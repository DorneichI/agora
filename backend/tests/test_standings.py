from datetime import date

from app.gameplay.models import Event, PredictionMarket, Race, Team
from app.leagues.models import League, LeagueUser
from app.leagues.repository import list_active_members
from app.models import User


async def _seed_league(db_session, owner_id, member_ids):
    """A league owned by owner_id, with one LeagueUser row per id in member_ids.

    member_ids must include owner_id if the owner is meant to appear in standings --
    this helper does not add the owner implicitly, so tests stay explicit about who is
    a member."""
    league = League(name="Standings League", created_by=owner_id, owner_id=owner_id)
    db_session.add(league)
    await db_session.commit()

    db_session.add_all([LeagueUser(league_id=league.id, user_id=user_id) for user_id in member_ids])
    await db_session.commit()
    return league.id


async def _seed_markets(db_session, creator_id, count):
    """`count` PredictionMarkets, each on its own Race, plus one Team to pick.

    One market per race is required: ix_predictionmarket_race_id_active makes race_id
    unique among live rows. Returns (team_id, [market_id, ...])."""
    team = Team(name="Crew", school="State", mascot="Otters", created_by=creator_id)
    event = Event(
        name="Regatta",
        description="Test regatta",
        format="head",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        created_by=creator_id,
    )
    db_session.add_all([team, event])
    await db_session.commit()

    races = [
        Race(
            name=f"Race {index}",
            event_id=event.id,
            boat_class="8+",
            level="varsity",
            created_by=creator_id,
        )
        for index in range(count)
    ]
    db_session.add_all(races)
    await db_session.commit()

    markets = [
        PredictionMarket(race_id=race.id, scoring_config={}, created_by=creator_id)
        for race in races
    ]
    db_session.add_all(markets)
    await db_session.commit()

    return team.id, [market.id for market in markets]


async def test_list_active_members_returns_members_with_users(db_session):
    owner = User(clerk_id="user_lam_1", email="lam1@example.com", username="owner")
    member = User(clerk_id="user_lam_2", email="lam2@example.com", username="member")
    db_session.add_all([owner, member])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id, member.id])

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id, member.id}
    assert {user.username for _membership, user in rows} == {"owner", "member"}
    assert all(membership.league_id == league_id for membership, _user in rows)


async def test_list_active_members_excludes_departed_member(db_session):
    owner = User(clerk_id="user_lam_3", email="lam3@example.com", username="owner2")
    leaver = User(clerk_id="user_lam_4", email="lam4@example.com", username="leaver")
    db_session.add_all([owner, leaver])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id, leaver.id])

    membership = next(
        m for m, u in await list_active_members(db_session, league_id) if u.id == leaver.id
    )
    await db_session.delete(membership)  # rewritten to a soft delete by app/soft_delete.py
    await db_session.commit()

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id}


async def test_list_active_members_excludes_other_leagues(db_session):
    owner = User(clerk_id="user_lam_5", email="lam5@example.com", username="owner3")
    outsider = User(clerk_id="user_lam_6", email="lam6@example.com", username="outsider")
    db_session.add_all([owner, outsider])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id])
    await _seed_league(db_session, outsider.id, [outsider.id])

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id}
