import time

import jwt
from sqlmodel import select

from app.clerk import CLERK_ISSUER
from app.models import User


async def test_me_without_token_returns_401(client):
    response = await client.get("/me")
    assert response.status_code == 401


async def test_me_with_garbage_token_returns_401(client):
    response = await client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_me_with_token_missing_profile_claims_returns_401(client, _rsa_keypair):
    """A validly-signed token that's missing the email/name claims (e.g. Clerk's session
    token template hasn't been customized per docs/architecture.md#auth) must not crash
    provisioning with an unhandled KeyError."""
    private_key, _public_key = _rsa_keypair
    payload = {
        "sub": "user_no_profile_claims",
        "iss": CLERK_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")

    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_creates_user_on_first_call(client, make_clerk_token, db_session):
    token = make_clerk_token(clerk_id="user_new", email="new@example.com", name="New Rower")

    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["clerk_id"] == "user_new"
    assert body["email"] == "new@example.com"
    assert body["username"] is None
    assert body["role"] == "user"

    rows = (
        (await db_session.execute(select(User).where(User.clerk_id == "user_new"))).scalars().all()
    )
    assert len(rows) == 1


async def test_me_returns_same_user_on_second_call(client, make_clerk_token):
    token = make_clerk_token(clerk_id="user_repeat", email="repeat@example.com", name="Repeat")

    first = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    second = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_concurrent_first_request_race_returns_existing_row(db_session, monkeypatch):
    """Simulates two near-simultaneous first-requests for the same new clerk_id: the initial
    SELECT misses (as if the other request hadn't committed yet when this one looked), the
    INSERT then hits the real unique-constraint violation because the other request already
    committed, and get_current_user must catch that and return the existing row instead of
    raising."""
    from app import deps
    from app.models import User

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

    claims = {"sub": "user_race", "email": "different@example.com", "name": "Different"}
    user = await deps.get_current_user(claims=claims, session=db_session)

    assert user.id == existing.id
    # resync-on-login applies on the race-recovery path too: the presented claims win
    assert user.email == "different@example.com"


async def test_me_resyncs_email_on_returning_login(client, make_clerk_token, db_session):
    """Clerk is the source of truth for profile fields -- a returning user's stored email
    must be refreshed from the newly-verified token claims, not left stale from whatever
    was true at first login."""
    first_token = make_clerk_token(clerk_id="user_resync", email="old@example.com", name="Old Name")
    first_response = await client.get("/me", headers={"Authorization": f"Bearer {first_token}"})
    assert first_response.status_code == 200
    original_id = first_response.json()["id"]

    second_token = make_clerk_token(
        clerk_id="user_resync", email="new@example.com", name="New Name"
    )
    second_response = await client.get("/me", headers={"Authorization": f"Bearer {second_token}"})

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["id"] == original_id
    assert body["email"] == "new@example.com"

    row = (
        await db_session.execute(select(User).where(User.clerk_id == "user_resync"))
    ).scalar_one()
    assert row.email == "new@example.com"


async def test_me_returning_login_with_no_profile_claims_keeps_stored_profile(
    client, make_clerk_token, _rsa_keypair
):
    """A returning user's token missing email/name claims (e.g. a claims-template
    regression) must not break login for an already-provisioned account -- resync is
    best-effort, not a hard requirement for authenticating an existing user."""
    first_token = make_clerk_token(
        clerk_id="user_resync_no_claims", email="kept@example.com", name="Kept Name"
    )
    first_response = await client.get("/me", headers={"Authorization": f"Bearer {first_token}"})
    assert first_response.status_code == 200

    private_key, _public_key = _rsa_keypair
    payload = {
        "sub": "user_resync_no_claims",
        "iss": CLERK_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    bare_token = jwt.encode(payload, private_key, algorithm="RS256")

    second_response = await client.get("/me", headers={"Authorization": f"Bearer {bare_token}"})

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["email"] == "kept@example.com"


async def test_me_email_already_used_by_different_clerk_id_returns_409(client, make_clerk_token):
    """Two different Clerk identities claiming the same email is a genuine conflict, not a
    same-identity race -- it must not be recovered as if it were (that would authenticate
    the second request as the first identity's account), and must not surface as a bare
    500 from an unhandled IntegrityError."""
    first_token = make_clerk_token(
        clerk_id="user_first_owner", email="shared@example.com", name="First Owner"
    )
    first_response = await client.get("/me", headers={"Authorization": f"Bearer {first_token}"})
    assert first_response.status_code == 200

    second_token = make_clerk_token(
        clerk_id="user_second_claimant", email="shared@example.com", name="Second Claimant"
    )
    second_response = await client.get("/me", headers={"Authorization": f"Bearer {second_token}"})

    assert second_response.status_code == 409
