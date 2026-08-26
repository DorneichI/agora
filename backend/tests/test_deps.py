import pytest
from fastapi import HTTPException

from app.deps import (
    require_admin,
    require_league_admin,
    require_league_member,
    require_league_owner,
    require_username,
)
from app.models import League, LeagueUser, User


async def test_require_admin_rejects_regular_user():
    user = User(clerk_id="user_regular", email="regular@example.com")

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user=user)

    assert exc_info.value.status_code == 403


async def test_require_admin_allows_admin_user():
    user = User(
        clerk_id="user_admin",
        email="admin@example.com",
        role="admin",
    )

    result = await require_admin(user=user)

    assert result is user


async def test_require_username_rejects_user_without_username():
    user = User(clerk_id="user_no_username", email="nousername@example.com")

    with pytest.raises(HTTPException) as exc_info:
        await require_username(user=user)

    assert exc_info.value.status_code == 403


async def test_require_league_admin_rejects_non_member(db_session):
    creator = User(clerk_id="user_rla_1", email="rla1@example.com")
    other = User(clerk_id="user_rla_2", email="rla2@example.com")
    db_session.add_all([creator, other])
    await db_session.commit()

    league = League(name="RLA League", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await require_league_admin(league_id=league.id, user=other, session=db_session)

    assert exc_info.value.status_code == 403


async def test_require_league_admin_rejects_plain_member(db_session):
    creator = User(clerk_id="user_rla_3", email="rla3@example.com")
    member = User(clerk_id="user_rla_4", email="rla4@example.com")
    db_session.add_all([creator, member])
    await db_session.commit()

    league = League(name="RLA League 2", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()
    db_session.add(LeagueUser(league_id=league.id, user_id=member.id, role="member"))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await require_league_admin(league_id=league.id, user=member, session=db_session)

    assert exc_info.value.status_code == 403


async def test_require_league_admin_allows_admin(db_session):
    creator = User(clerk_id="user_rla_5", email="rla5@example.com")
    db_session.add(creator)
    await db_session.commit()

    league = League(name="RLA League 3", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()
    db_session.add(LeagueUser(league_id=league.id, user_id=creator.id, role="admin"))
    await db_session.commit()

    result = await require_league_admin(league_id=league.id, user=creator, session=db_session)

    assert result.id == league.id


async def test_require_league_admin_missing_league_returns_404(db_session):
    user = User(clerk_id="user_rla_6", email="rla6@example.com")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await require_league_admin(league_id=999999, user=user, session=db_session)

    assert exc_info.value.status_code == 404


async def test_require_league_owner_rejects_non_owner_admin(db_session):
    owner = User(clerk_id="user_rlo_1", email="rlo1@example.com")
    admin = User(clerk_id="user_rlo_2", email="rlo2@example.com")
    db_session.add_all([owner, admin])
    await db_session.commit()

    league = League(name="RLO League", created_by=owner.id, owner_id=owner.id)
    db_session.add(league)
    await db_session.commit()
    db_session.add(LeagueUser(league_id=league.id, user_id=admin.id, role="admin"))
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await require_league_owner(league_id=league.id, user=admin, session=db_session)

    assert exc_info.value.status_code == 403


async def test_require_league_owner_allows_owner(db_session):
    owner = User(clerk_id="user_rlo_3", email="rlo3@example.com")
    db_session.add(owner)
    await db_session.commit()

    league = League(name="RLO League 2", created_by=owner.id, owner_id=owner.id)
    db_session.add(league)
    await db_session.commit()

    result = await require_league_owner(league_id=league.id, user=owner, session=db_session)

    assert result.id == league.id


async def test_require_username_allows_user_with_username():
    user = User(clerk_id="user_has_username", email="hasusername@example.com", username="rower1")

    result = await require_username(user=user)

    assert result is user


async def test_require_league_member_rejects_non_member(db_session):
    creator = User(clerk_id="user_rlm_1", email="rlm1@example.com")
    other = User(clerk_id="user_rlm_2", email="rlm2@example.com")
    db_session.add_all([creator, other])
    await db_session.commit()

    league = League(name="RLM League", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await require_league_member(league_id=league.id, user=other, session=db_session)

    assert exc_info.value.status_code == 403


async def test_require_league_member_allows_plain_member(db_session):
    creator = User(clerk_id="user_rlm_3", email="rlm3@example.com")
    member = User(clerk_id="user_rlm_4", email="rlm4@example.com")
    db_session.add_all([creator, member])
    await db_session.commit()

    league = League(name="RLM League 2", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()

    db_session.add(LeagueUser(league_id=league.id, user_id=member.id))
    await db_session.commit()

    result = await require_league_member(league_id=league.id, user=member, session=db_session)

    assert result.id == league.id
