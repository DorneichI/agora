import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User


async def test_user_has_soft_delete_fields_and_clerk_id(db_session):
    user = User(clerk_id="user_abc", email="rower@example.com", display_name="Rower Example")
    db_session.add(user)
    await db_session.commit()

    assert user.id is not None
    assert user.created_at is not None
    assert user.deleted_at is None


async def test_duplicate_active_clerk_id_rejected(db_session):
    db_session.add(User(clerk_id="user_dup", email="a@example.com", display_name="A"))
    await db_session.commit()

    db_session.add(User(clerk_id="user_dup", email="b@example.com", display_name="B"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_duplicate_active_email_rejected(db_session):
    db_session.add(User(clerk_id="user_1", email="dup@example.com", display_name="A"))
    await db_session.commit()

    db_session.add(User(clerk_id="user_2", email="dup@example.com", display_name="B"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
