import json
import time

import jwt
import pytest
from fastapi import HTTPException

from app.auth.clerk_provider import CLERK_ISSUER, ClerkIdentityProvider


def test_valid_token_returns_identity(make_clerk_token):
    token = make_clerk_token(clerk_id="user_1", email="a@example.com", name="A")

    identity = ClerkIdentityProvider().verify(token)

    assert identity.external_id == "user_1"
    assert identity.email == "a@example.com"


def test_token_without_email_claim_returns_identity_with_none_email(_rsa_keypair):
    private_key, _public_key = _rsa_keypair
    payload = {
        "sub": "user_no_email",
        "iss": CLERK_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")

    identity = ClerkIdentityProvider().verify(token)

    assert identity.external_id == "user_no_email"
    assert identity.email is None


def test_expired_token_rejected(make_clerk_token):
    token = make_clerk_token(exp=int(time.time()) - 10)

    with pytest.raises(HTTPException) as exc_info:
        ClerkIdentityProvider().verify(token)
    assert exc_info.value.status_code == 401


def test_wrong_issuer_rejected(make_clerk_token):
    token = make_clerk_token(iss="https://not-us.clerk.accounts.dev")

    with pytest.raises(HTTPException) as exc_info:
        ClerkIdentityProvider().verify(token)
    assert exc_info.value.status_code == 401


def test_garbage_token_rejected():
    with pytest.raises(HTTPException) as exc_info:
        ClerkIdentityProvider().verify("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_jwks_fetch_returning_non_json_rejected(monkeypatch):
    from app.auth.clerk_provider import _jwk_client

    def _raise_json_error(token):
        raise json.JSONDecodeError("Expecting value", "not json", 0)

    monkeypatch.setattr(_jwk_client, "get_signing_key_from_jwt", _raise_json_error)

    with pytest.raises(HTTPException) as exc_info:
        ClerkIdentityProvider().verify("irrelevant-token")
    assert exc_info.value.status_code == 401
