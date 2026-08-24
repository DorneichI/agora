import pytest
from sqlmodel import select

from app.models import User
from scripts.promote_admin import UserNotFoundError, promote_to_admin


async def test_promote_to_admin_sets_role_on_existing_user(db_session):
    user = User(clerk_id="user_promote", email="promote@example.com", display_name="Promote Me")
    db_session.add(user)
    await db_session.commit()

    promoted = await promote_to_admin(db_session, "promote@example.com")

    assert promoted.role == "admin"

    row = (
        await db_session.execute(select(User).where(User.email == "promote@example.com"))
    ).scalar_one()
    assert row.role == "admin"


async def test_promote_to_admin_raises_clearly_for_unknown_email(db_session):
    with pytest.raises(UserNotFoundError):
        await promote_to_admin(db_session, "nobody@example.com")

    rows = (
        (await db_session.execute(select(User).where(User.email == "nobody@example.com")))
        .scalars()
        .all()
    )
    assert rows == []
