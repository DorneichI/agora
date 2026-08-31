from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.clerk_provider import ClerkIdentityProvider
from app.auth.ports import AuthenticatedIdentity, IdentityProvider
from app.db import get_session
from app.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_identity_provider() -> IdentityProvider:
    return ClerkIdentityProvider()


def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> AuthenticatedIdentity:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return provider.verify(credentials.credentials)


async def _resync_profile_from_claims(
    session: AsyncSession, user: User, identity: AuthenticatedIdentity
) -> User:
    """Clerk is the source of truth for profile fields, so refresh a returning user's
    stored email from the presented token's claims. Best-effort: a token missing this
    claim (e.g. a claims-template regression) shouldn't break login for an
    already-provisioned account, so just leave the stored profile untouched in that case.
    """
    if identity.email is None or user.email == identity.email:
        return user

    user.email = identity.email
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A different Clerk identity already owns this email -- same collision
        # get_current_user's create path guards against, just reached via a returning
        # user's email changing at the IdP instead of a first login.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already associated with a different account",
        ) from None
    await session.refresh(user)
    return user


async def get_current_user(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    session: AsyncSession = Depends(get_session),
) -> User:
    existing = (
        await session.execute(select(User).where(User.clerk_id == identity.external_id))
    ).scalar_one_or_none()
    if existing is not None:
        return await _resync_profile_from_claims(session, existing, identity)

    if identity.email is None:
        # Expected if Clerk's session-token template hasn't been customized to add this
        # claim (see docs/architecture.md#auth) -- surface a clear error instead of silently
        # creating a profile-less user.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing required profile claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = User(clerk_id=identity.external_id, email=identity.email)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Recover the same-clerk_id race: two near-simultaneous first logins for the same
        # Clerk identity both missed the initial SELECT, the other one's INSERT already
        # committed, so return its row.
        existing = (
            await session.execute(select(User).where(User.clerk_id == identity.external_id))
        ).scalar_one_or_none()
        if existing is not None:
            return await _resync_profile_from_claims(session, existing, identity)
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


async def require_username(user: User = Depends(get_current_user)) -> User:
    if user.username is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Username must be set before accessing this resource",
        )
    return user
