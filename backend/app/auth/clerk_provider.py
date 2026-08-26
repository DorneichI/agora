import json
import os

import jwt
from fastapi import HTTPException, status

from app.auth.ports import AuthenticatedIdentity

CLERK_ISSUER = os.environ["CLERK_ISSUER"]
_JWKS_URL = f"{CLERK_ISSUER}/.well-known/jwks.json"
_jwk_client = jwt.PyJWKClient(_JWKS_URL)


class ClerkIdentityProvider:
    def verify(self, token: str) -> AuthenticatedIdentity:
        """Verify Clerk JWT signature, issuer, expiry; return caller's identity."""
        try:
            signing_key = _jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=CLERK_ISSUER,
                # Clerk session tokens aren't validated by audience (there's no `audience=`
                # value to compare against here) -- without `verify_aud: False`, PyJWT still
                # rejects the token the moment it happens to carry a non-empty "aud" claim
                # (e.g. if a future custom session-claims template adds one), which would lock
                # out every user with a misleading "invalid token" error instead of an obvious
                # config error.
                options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
        except (jwt.PyJWTError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return AuthenticatedIdentity(external_id=claims["sub"], email=claims.get("email"))
