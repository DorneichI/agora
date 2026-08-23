import os

import jwt
from fastapi import HTTPException, status

CLERK_ISSUER = os.environ["CLERK_ISSUER"]
_JWKS_URL = f"{CLERK_ISSUER}/.well-known/jwks.json"
_jwk_client = jwt.PyJWKClient(_JWKS_URL)


def verify_clerk_jwt(token: str) -> dict:
    """Verify a Clerk-issued JWT's signature, issuer, and expiry; return its claims."""
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLERK_ISSUER,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
