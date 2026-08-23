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


async def get_current_user(
    claims: dict = Depends(get_current_claims),
    session: AsyncSession = Depends(get_session),
) -> User:
    clerk_id = claims["sub"]

    existing = (
        await session.execute(select(User).where(User.clerk_id == clerk_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(clerk_id=clerk_id, email=claims["email"], display_name=claims["name"])
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(select(User).where(User.clerk_id == clerk_id))
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing

    await session.refresh(user)
    return user
