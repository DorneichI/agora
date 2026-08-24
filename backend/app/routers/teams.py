from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Team, TeamRead, User

router = APIRouter()


class TeamCreate(SQLModel):
    name: str
    school: str
    mascot: str
    image_url: str | None = None


@router.post("/teams", response_model=TeamRead)
async def create_team(
    body: TeamCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Team:
    team = Team(
        name=body.name,
        school=body.school,
        mascot=body.mascot,
        image_url=body.image_url,
        created_by=user.id,
    )
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


@router.get("/teams/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Team:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Team]:
    return list((await session.execute(select(Team))).scalars().all())
