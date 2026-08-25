from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.crud_helpers import assert_not_referenced, get_or_404
from app.db import get_session
from app.deps import require_admin, require_username
from app.models import RaceEntry, Team, TeamRead, User

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
    return team


@router.get("/teams/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Team:
    return await get_or_404(session, Team, team_id)


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(
    user: User = Depends(require_username),
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
    team = await get_or_404(session, Team, team_id)

    updates = body.model_dump(exclude_unset=True)
    if updates:
        for field, value in updates.items():
            setattr(team, field, value)
        team.updated_by = user.id
        session.add(team)
        await session.commit()
    return team


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    team = await get_or_404(session, Team, team_id)
    await assert_not_referenced(session, RaceEntry, "team_id", team_id, "Team")

    await session.delete(team)
    await session.commit()
