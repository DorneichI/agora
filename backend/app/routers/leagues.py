from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user
from app.models import League, LeagueRead, LeagueUser, User

router = APIRouter()


class LeagueCreate(SQLModel):
    name: str


@router.post("/leagues", response_model=LeagueRead)
async def create_league(
    body: LeagueCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = League(name=body.name, created_by=user.id)
    session.add(league)
    await session.flush()

    session.add(LeagueUser(league_id=league.id, user_id=user.id))
    await session.commit()
    await session.refresh(league)
    return league


@router.get("/leagues/{league_id}", response_model=LeagueRead)
async def get_league(
    league_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league


@router.post("/leagues/{league_id}/join", status_code=status.HTTP_204_NO_CONTENT)
async def join_league(
    league_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    membership = (
        await session.execute(
            select(LeagueUser)
            .where(LeagueUser.league_id == league_id, LeagueUser.user_id == user.id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

    if membership is None:
        session.add(LeagueUser(league_id=league_id, user_id=user.id))
        await session.commit()
    elif membership.deleted_at is not None:
        membership.deleted_at = None
        session.add(membership)
        await session.commit()


@router.post("/leagues/{league_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_league(
    league_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    membership = (
        await session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == user.id
            )
        )
    ).scalar_one_or_none()

    if membership is not None:
        await session.delete(membership)
        await session.commit()
