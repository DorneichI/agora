from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.clerk import verify_clerk_jwt
from app.db import get_session
from app.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_clerk_jwt(credentials.credentials)


async def _resync_profile_from_claims(session: AsyncSession, user: User, claims: dict) -> User:
    """Clerk is the source of truth for profile fields, so refresh a returning user's
    stored email/display_name from the presented token's claims. Best-effort: a token
    missing these claims (e.g. a claims-template regression) shouldn't break login for an
    already-provisioned account, so just leave the stored profile untouched in that case.
    """
    email = claims.get("email")
    display_name = claims.get("name")
    if email is None or display_name is None:
        return user
    if user.email == email and user.display_name == display_name:
        return user

    user.email = email
    user.display_name = display_name
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_current_user(
    claims: dict = Depends(get_current_claims),
    session: AsyncSession = Depends(get_session),
) -> User:
    clerk_id = claims["sub"]

    existing = (
        await session.execute(select(User).where(User.clerk_id == clerk_id))
    ).scalar_one_or_none()
    if existing is not None:
        return await _resync_profile_from_claims(session, existing, claims)

    try:
        email = claims["email"]
        display_name = claims["name"]
    except KeyError as exc:
        # Expected if Clerk's session-token template hasn't been customized to add these
        # claims (see docs/architecture.md#auth) -- surface a clear error instead of a bare
        # 500 from an uncaught KeyError.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing required profile claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = User(clerk_id=clerk_id, email=email, display_name=display_name)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Recover the same-clerk_id race: two near-simultaneous first logins for the same
        # Clerk identity both missed the initial SELECT, the other one's INSERT already
        # committed, so return its row.
        existing = (
            await session.execute(select(User).where(User.clerk_id == clerk_id))
        ).scalar_one_or_none()
        if existing is not None:
            return await _resync_profile_from_claims(session, existing, claims)
        # Not a clerk_id race: the INSERT collided on the email unique index instead, which
        # means a *different* Clerk identity already owns this email. Don't fall through to
        # a bare 500, and don't return the other identity's row -- that would authenticate
        # this request as the wrong account.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already associated with a different account",
        ) from None

    await session.refresh(user)
    return user
