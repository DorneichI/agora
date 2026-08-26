import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_active_league_membership, require_league_member, require_username
from app.models import League, LeagueInvite, LeagueInviteRead, User

router = APIRouter()

INVITE_LIFETIME = timedelta(days=7)

# Postgres SQLSTATE for a unique-constraint violation.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


class InviteCreate(SQLModel):
    target_username: str | None = None


def _is_invite_code_collision(exc: IntegrityError) -> bool:
    """Distinguish "the generated code collided with the partial unique index" from any
    other IntegrityError (e.g. a bad FK) so the retry loop below only retries the case it
    actually knows how to recover from.

    SQLAlchemy's asyncpg dialect wraps the driver error and re-raises it with
    `raise translated_error from error`, so the original `asyncpg.exceptions.
    UniqueViolationError` -- which carries the Postgres diagnostic fields `sqlstate` and
    `constraint_name` -- is available via `exc.orig.__cause__`. `exc.orig` itself (SQLAlchemy's
    thin DBAPI wrapper) only exposes `sqlstate`/`pgcode`, not `constraint_name`. Verified
    empirically against a real Postgres/asyncpg unique-violation.
    """
    cause = getattr(exc.orig, "__cause__", None)
    return (
        getattr(cause, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE
        and getattr(cause, "constraint_name", None) == "ix_leagueinvite_code_active"
    )


@router.post("/leagues/{league_id}/invites", response_model=LeagueInviteRead)
async def create_invite(
    league_id: int,
    body: InviteCreate,
    league: League = Depends(require_league_member),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> LeagueInvite:
    is_owner = user.id == league.owner_id
    if league.invite_policy == "owner_only" and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the league owner can create invites",
        )
    if league.invite_policy == "admins_only" and not is_owner:
        membership = await get_active_league_membership(session, league_id, user.id)
        if membership is None or membership.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="League admin privileges required to create invites",
            )

    if league.visibility == "public":
        if body.target_username is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="target_username must be omitted for a public league invite",
            )
        target_user_id = None
    else:
        if body.target_username is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="target_username is required for a private league invite",
            )
        target_user = (
            await session.execute(select(User).where(User.username == body.target_username))
        ).scalar_one_or_none()
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user found with that username",
            )
        target_user_id = target_user.id

    # Captured once, before the loop: a collision's rollback (below) expires every ORM
    # object tracked by this request's session, including `user`. Re-reading `user.id`
    # inside the loop after that would be a synchronous lazy-load on an expired attribute,
    # which raises MissingGreenlet outside of an awaited call. Reusing this plain int
    # instead sidesteps that -- it needs no DB round trip and doesn't change between
    # attempts anyway.
    created_by = user.id

    for _attempt in range(5):
        invite = LeagueInvite(
            league_id=league_id,
            code=secrets.token_urlsafe(32),
            created_by=created_by,
            target_user_id=target_user_id,
            expires_at=datetime.now(UTC) + INVITE_LIFETIME,
        )
        session.add(invite)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if _is_invite_code_collision(exc):
                continue
            raise
        await session.refresh(invite)
        return invite

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate a unique invite code",
    )
