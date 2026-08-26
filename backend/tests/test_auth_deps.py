import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.clerk_provider import ClerkIdentityProvider
from app.auth.deps import (
    get_current_identity,
    get_current_user,
    get_identity_provider,
    require_username,
)
from app.auth.ports import AuthenticatedIdentity
from app.models import User


class _StubProvider:
    def verify(self, token: str) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(external_id=f"verified-{token}", email="stub@example.com")


def test_get_identity_provider_returns_clerk_identity_provider():
    provider = get_identity_provider()

    assert isinstance(provider, ClerkIdentityProvider)


def test_get_current_identity_without_credentials_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        get_current_identity(credentials=None, provider=_StubProvider())

    assert exc_info.value.status_code == 401


def test_get_current_identity_delegates_to_provider():
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-123")

    identity = get_current_identity(credentials=credentials, provider=_StubProvider())

    assert identity.external_id == "verified-tok-123"
    assert identity.email == "stub@example.com"


async def test_require_username_rejects_user_without_username():
    user = User(clerk_id="user_no_username", email="nousername@example.com")

    with pytest.raises(HTTPException) as exc_info:
        await require_username(user=user)

    assert exc_info.value.status_code == 403


async def test_require_username_allows_user_with_username():
    user = User(clerk_id="user_has_username", email="hasusername@example.com", username="rower1")

    result = await require_username(user=user)

    assert result is user


async def test_concurrent_first_request_race_returns_existing_row(db_session, monkeypatch):
    """Simulates two near-simultaneous first-requests for the same new clerk_id: the initial
    SELECT misses (as if the other request hadn't committed yet when this one looked), the
    INSERT then hits the real unique-constraint violation because the other request already
    committed, and get_current_user must catch that and return the existing row instead of
    raising."""
    existing = User(clerk_id="user_race", email="race@example.com")
    db_session.add(existing)
    await db_session.commit()

    original_execute = db_session.execute
    call_count = 0

    async def fake_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:

            class _EmptyResult:
                def scalar_one_or_none(self):
                    return None

            return _EmptyResult()
        return await original_execute(*args, **kwargs)

    monkeypatch.setattr(db_session, "execute", fake_execute)

    identity = AuthenticatedIdentity(external_id="user_race", email="different@example.com")
    user = await get_current_user(identity=identity, session=db_session)

    assert user.id == existing.id
    # resync-on-login applies on the race-recovery path too: the presented claims win
    assert user.email == "different@example.com"
