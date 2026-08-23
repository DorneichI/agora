import time

import pytest
from fastapi import HTTPException

from app.clerk import verify_clerk_jwt


def test_valid_token_returns_claims(make_clerk_token):
    token = make_clerk_token(clerk_id="user_1", email="a@example.com", name="A")

    claims = verify_clerk_jwt(token)

    assert claims["sub"] == "user_1"
    assert claims["email"] == "a@example.com"
    assert claims["name"] == "A"


def test_expired_token_rejected(make_clerk_token):
    token = make_clerk_token(exp=int(time.time()) - 10)

    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_jwt(token)
    assert exc_info.value.status_code == 401


def test_wrong_issuer_rejected(make_clerk_token):
    token = make_clerk_token(iss="https://not-us.clerk.accounts.dev")

    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_jwt(token)
    assert exc_info.value.status_code == 401


def test_garbage_token_rejected():
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_jwt("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_jwks_fetch_returning_non_json_rejected(monkeypatch):
    import json as json_module

    from app.clerk import _jwk_client, verify_clerk_jwt

    def _raise_json_error(token):
        raise json_module.JSONDecodeError("Expecting value", "not json", 0)

    monkeypatch.setattr(_jwk_client, "get_signing_key_from_jwt", _raise_json_error)

    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_jwt("irrelevant-token")
    assert exc_info.value.status_code == 401
