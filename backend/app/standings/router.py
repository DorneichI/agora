"""League standings.

This lives in its own app.standings package, not app.leagues or app.gameplay: computing a
league's standings requires both league membership (app.leagues) and aggregated prediction
points (app.gameplay), and pyproject.toml's import-linter contract makes those two domains
mutually independent (`independence` contract) so neither may import the other.
app.standings is the one place allowed to depend on both -- its entire purpose is bridging
them. See backend/CLAUDE.md's "Domain modules" section for the general rule.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_username
from app.db import get_session
from app.gameplay import repository
from app.leagues.deps import require_league_member
from app.leagues.models import League
from app.leagues.repository import list_active_members
from app.models import User
from app.standings.models import LeagueStandingRead

router = APIRouter()


@router.get("/leagues/{league_id}/standings", response_model=list[LeagueStandingRead])
async def list_league_standings(
    league: League = Depends(require_league_member),
    caller: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[LeagueStandingRead]:
    """Season-to-date points for every member of the league, highest first.

    require_league_member reads league_id straight off the path, and supplies the 404 for
    a missing league and the 403 for a non-member -- so this route declares no league_id
    parameter of its own.

    `caller` is unused in the body: require_league_member already depends on
    require_username internally, so this doesn't change behavior (FastAPI caches the
    dependency resolution, it isn't re-run). It's declared as a top-level dependency solely
    so this route is visible to tests/test_username_route_gating.py's regression guard,
    which only inspects each route's immediate dependencies, not transitive ones -- see the
    same pattern on every route in app/leagues/routers/leagues.py that depends on
    require_league_admin/require_league_owner.

    Two queries merged in Python rather than one LEFT JOIN: app/soft_delete.py injects a
    `deleted_at IS NULL` criteria into every select as a WHERE predicate, which on an
    outer join would degrade it to an inner join and silently drop exactly the members who
    have no predictions yet.
    """
    members = await list_active_members(session, league.id)
    totals = await repository.sum_settled_points_by_user(
        session, [user.id for _membership, user in members]
    )

    standings = [
        LeagueStandingRead(
            user_id=user.id,
            username=user.username,
            points=totals.get(user.id, 0.0),
        )
        for _membership, user in members
    ]
    # Points descending, then username ascending. The tie-break is not cosmetic: without
    # it Postgres may return tied rows in a different order run to run, making both tests
    # and clients flaky.
    standings.sort(key=lambda row: (-row.points, row.username or ""))
    return standings
