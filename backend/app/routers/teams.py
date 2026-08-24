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


class TeamUpdate(SQLModel):
    name: str | None = None
    school: str | None = None
    mascot: str | None = None
    image_url: str | None = None


@router.patch("/teams/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Team:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    team.updated_by = user.id

    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    await session.delete(team)
    await session.commit()
