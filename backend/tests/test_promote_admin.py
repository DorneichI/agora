import pytest
from sqlmodel import select

from app.models import User
from scripts.promote_admin import UserNotFoundError, promote_to_admin


async def test_promote_to_admin_sets_role_on_existing_user(db_session):
    user = User(clerk_id="user_promote", email="promote@example.com")
    db_session.add(user)
    await db_session.commit()

    promoted = await promote_to_admin(db_session, "promote@example.com")

    assert promoted.role == "admin"

    row = (
        await db_session.execute(select(User).where(User.email == "promote@example.com"))
    ).scalar_one()
    assert row.role == "admin"


async def test_promote_to_admin_matches_email_case_insensitively(db_session):
    """Clerk tokens carry email verbatim (never lowercased on write, unlike username), so an
    operator typing the address in a different case than Clerk issued it must still match."""
    user = User(clerk_id="user_promote_case", email="Imm.Dorneich@Example.com")
    db_session.add(user)
    await db_session.commit()

    promoted = await promote_to_admin(db_session, "imm.dorneich@example.com")

    assert promoted.role == "admin"
    assert promoted.email == "Imm.Dorneich@Example.com"


async def test_promote_to_admin_raises_clearly_for_unknown_email(db_session):
    with pytest.raises(UserNotFoundError):
        await promote_to_admin(db_session, "nobody@example.com")

    rows = (
        (await db_session.execute(select(User).where(User.email == "nobody@example.com")))
        .scalars()
        .all()
    )
    assert rows == []
