import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User


async def test_user_has_soft_delete_fields_and_clerk_id(db_session):
    user = User(clerk_id="user_abc", email="rower@example.com")
    db_session.add(user)
    await db_session.commit()

    assert user.id is not None
    assert user.created_at is not None
    assert user.deleted_at is None


async def test_duplicate_active_clerk_id_rejected(db_session):
    db_session.add(User(clerk_id="user_dup", email="a@example.com"))
    await db_session.commit()

    db_session.add(User(clerk_id="user_dup", email="b@example.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_duplicate_active_email_rejected(db_session):
    db_session.add(User(clerk_id="user_1", email="dup@example.com"))
    await db_session.commit()

    db_session.add(User(clerk_id="user_2", email="dup@example.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_defaults_to_role_user(db_session):
    user = User(clerk_id="user_role_default", email="default@example.com")
    db_session.add(user)
    await db_session.commit()

    assert user.role == "user"


async def test_user_username_defaults_to_none(db_session):
    user = User(clerk_id="user_no_username", email="nousername@example.com")
    db_session.add(user)
    await db_session.commit()

    assert user.username is None


async def test_duplicate_active_username_rejected(db_session):
    db_session.add(User(clerk_id="user_uname_1", email="uname1@example.com", username="rower1"))
    await db_session.commit()

    db_session.add(User(clerk_id="user_uname_2", email="uname2@example.com", username="rower1"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
