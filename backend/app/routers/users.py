from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import get_current_user
from app.db import get_session
from app.models import User, UserRead
from app.models.user import USERNAME_PATTERN

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user


class UsernameSet(SQLModel):
    username: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        value = value.lower()
        if not USERNAME_PATTERN.match(value):
            raise ValueError(
                "username must be 3-20 characters: lowercase letters, digits, or underscores"
            )
        return value


@router.post("/me/username", response_model=UserRead)
async def set_username(
    body: UsernameSet,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    if user.username is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already set")

    user.username = body.username
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already taken"
        ) from None
    await session.refresh(user)
    return user
