import pytest
from sqlalchemy.exc import IntegrityError

from app.models import League, LeagueUser, User


async def test_league_has_soft_delete_fields_and_created_by(db_session):
    creator = User(clerk_id="user_league_owner", email="owner@example.com", display_name="Owner")
    db_session.add(creator)
    await db_session.commit()

    league = League(name="Head of the Charles", created_by=creator.id)
    db_session.add(league)
    await db_session.commit()

    assert league.id is not None
    assert league.created_at is not None
    assert league.deleted_at is None
    assert league.created_by == creator.id


async def test_leagueuser_links_league_and_user(db_session):
    creator = User(clerk_id="user_lu_1", email="lu1@example.com", display_name="LU One")
    db_session.add(creator)
    await db_session.commit()

    league = League(name="Boston Sprints", created_by=creator.id)
    db_session.add(league)
    await db_session.commit()

    membership = LeagueUser(league_id=league.id, user_id=creator.id)
    db_session.add(membership)
    await db_session.commit()

    assert membership.id is not None
    assert membership.deleted_at is None


async def test_duplicate_active_membership_rejected(db_session):
    creator = User(clerk_id="user_lu_2", email="lu2@example.com", display_name="LU Two")
    db_session.add(creator)
    await db_session.commit()

    league = League(name="Charles River Regatta", created_by=creator.id)
    db_session.add(league)
    await db_session.commit()

    db_session.add(LeagueUser(league_id=league.id, user_id=creator.id))
    await db_session.commit()

    db_session.add(LeagueUser(league_id=league.id, user_id=creator.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_rejoin_after_leave_allowed_by_partial_index(db_session):
    creator = User(clerk_id="user_lu_3", email="lu3@example.com", display_name="LU Three")
    db_session.add(creator)
    await db_session.commit()

    league = League(name="Rowing Classic", created_by=creator.id)
    db_session.add(league)
    await db_session.commit()

    first_membership = LeagueUser(league_id=league.id, user_id=creator.id)
    db_session.add(first_membership)
    await db_session.commit()

    await db_session.delete(first_membership)
    await db_session.commit()

    second_membership = LeagueUser(league_id=league.id, user_id=creator.id)
    db_session.add(second_membership)
    await db_session.commit()  # would raise IntegrityError if the index weren't partial

    assert second_membership.id is not None
    assert second_membership.id != first_membership.id
