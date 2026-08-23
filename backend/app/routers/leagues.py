from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.db import get_session
from app.deps import get_current_user
from app.models import League, LeagueUser, User

router = APIRouter()


class LeagueCreate(SQLModel):
    name: str


@router.post("/leagues", response_model=League)
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
