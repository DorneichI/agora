import pytest
from fastapi import HTTPException

from app.deps import require_admin, require_username
from app.models import User


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


async def test_require_username_allows_user_with_username():
    user = User(clerk_id="user_has_username", email="hasusername@example.com", username="rower1")

    result = await require_username(user=user)

    assert result is user
