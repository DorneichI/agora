from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import League, LeagueInvite, User


async def _make_league(db_session, clerk_id, email):
    creator = User(clerk_id=clerk_id, email=email)
    db_session.add(creator)
    await db_session.commit()

    league = League(name="Invite Test League", created_by=creator.id, owner_id=creator.id)
    db_session.add(league)
    await db_session.commit()

    return creator, league


async def test_leagueinvite_has_soft_delete_fields_and_defaults(db_session):
    creator, league = await _make_league(db_session, "user_li_1", "li1@example.com")

    invite = LeagueInvite(
        league_id=league.id,
        code="abc123",
        created_by=creator.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()

    assert invite.id is not None
    assert invite.created_at is not None
    assert invite.deleted_at is None
    assert invite.target_user_id is None
    assert invite.redeemed_at is None
    assert invite.revoked_at is None


async def test_duplicate_active_code_rejected(db_session):
    creator, league = await _make_league(db_session, "user_li_2", "li2@example.com")
    expires_at = datetime.now(UTC) + timedelta(days=7)

    db_session.add(
        LeagueInvite(
            league_id=league.id, code="dup-code", created_by=creator.id, expires_at=expires_at
        )
    )
    await db_session.commit()

    db_session.add(
        LeagueInvite(
            league_id=league.id, code="dup-code", created_by=creator.id, expires_at=expires_at
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_code_reusable_after_hard_delete_by_partial_index(db_session):
    """Not a real-world scenario (revoke never calls session.delete on the row), but proves the
    unique index is scoped to deleted_at IS NULL rather than a plain unique constraint, matching
    every other soft-deletable table's convention."""
    creator, league = await _make_league(db_session, "user_li_3", "li3@example.com")
    expires_at = datetime.now(UTC) + timedelta(days=7)

    first = LeagueInvite(
        league_id=league.id, code="reused-code", created_by=creator.id, expires_at=expires_at
    )
    db_session.add(first)
    await db_session.commit()

    await db_session.delete(first)
    await db_session.commit()

    second = LeagueInvite(
        league_id=league.id, code="reused-code", created_by=creator.id, expires_at=expires_at
    )
    db_session.add(second)
    await db_session.commit()  # would raise IntegrityError if the index weren't partial

    assert second.id is not None
    assert second.id != first.id
