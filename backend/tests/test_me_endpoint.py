import time

import jwt
from sqlmodel import select

from app.auth.clerk_provider import CLERK_ISSUER
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


async def test_set_username_succeeds(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_set_username", email="setusername@example.com", name="Set Username"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/me/username",
        json={"username": "rower123"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "rower123"


async def test_set_username_lowercases_input(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_set_username_case", email="setusernamecase@example.com", name="Case"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/me/username",
        json={"username": "RowerCase"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "rowercase"


async def test_set_username_twice_returns_409(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_set_username_twice", email="setusernametwice@example.com", name="Twice"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    first = await client.post(
        "/me/username",
        json={"username": "firstname"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/me/username",
        json={"username": "secondname"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert second.status_code == 409


async def test_set_username_case_insensitive_collision_returns_409(client, make_clerk_token):
    first_token = make_clerk_token(
        clerk_id="user_username_collision_1",
        email="usernamecollision1@example.com",
        name="First",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {first_token}"})
    await client.post(
        "/me/username",
        json={"username": "alice"},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    second_token = make_clerk_token(
        clerk_id="user_username_collision_2",
        email="usernamecollision2@example.com",
        name="Second",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {second_token}"})

    response = await client.post(
        "/me/username",
        json={"username": "Alice"},
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert response.status_code == 409


async def test_set_username_invalid_format_returns_422(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_set_username_invalid",
        email="setusernameinvalid@example.com",
        name="Invalid",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/me/username",
        json={"username": "no spaces allowed"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_set_username_with_trailing_newline_returns_422(client, make_clerk_token):
    """Regression test: `^...$` (unlike `\\A...\\Z`) matches immediately before a trailing
    newline, so "alice\\n" used to pass validation as a distinct username from "alice"."""
    token = make_clerk_token(
        clerk_id="user_set_username_trailing_newline",
        email="setusernametrailingnewline@example.com",
        name="Trailing Newline",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/me/username",
        json={"username": "alice\n"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_set_username_too_short_returns_422(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_set_username_short", email="setusernameshort@example.com", name="Short"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/me/username",
        json={"username": "ab"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_set_username_without_token_returns_401(client):
    response = await client.post("/me/username", json={"username": "rower123"})

    assert response.status_code == 401
