from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.auth.deps import require_username
from app.crud_helpers import get_or_404, validate_fk_exists
from app.db import get_session
from app.deps import require_admin
from app.models import Race, RaceEntry, RaceEntryRead, Team, User

router = APIRouter()

RaceEntryStatus = Literal["finished", "dnf", "dns", "dq"]


async def _validate_race_id(race_id: int, session: AsyncSession) -> None:
    await validate_fk_exists(session, Race, race_id, "race_id")


async def _validate_team_id(team_id: int, session: AsyncSession) -> None:
    await validate_fk_exists(session, Team, team_id, "team_id")


class RaceEntryCreate(SQLModel):
    race_id: int
    team_id: int
    level: str
    time: float | None = None
    status: RaceEntryStatus = "dns"


@router.post("/race-entries", response_model=RaceEntryRead)
async def create_race_entry(
    body: RaceEntryCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RaceEntry:
    await _validate_race_id(body.race_id, session)
    await _validate_team_id(body.team_id, session)

    race_entry = RaceEntry(
        race_id=body.race_id,
        team_id=body.team_id,
        level=body.level,
        time=body.time,
        status=body.status,
        created_by=user.id,
    )
    session.add(race_entry)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active RaceEntry already exists for this race_id and team_id",
        ) from exc
    return race_entry


@router.get("/race-entries/{race_entry_id}", response_model=RaceEntryRead)
async def get_race_entry(
    race_entry_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> RaceEntry:
    return await get_or_404(session, RaceEntry, race_entry_id)


@router.get("/race-entries", response_model=list[RaceEntryRead])
async def list_race_entries(
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[RaceEntry]:
    return list((await session.execute(select(RaceEntry))).scalars().all())


class RaceEntryUpdate(SQLModel):
    level: str | None = None
    time: float | None = None
    status: RaceEntryStatus | None = None


@router.patch("/race-entries/{race_entry_id}", response_model=RaceEntryRead)
async def update_race_entry(
    race_entry_id: int,
    body: RaceEntryUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RaceEntry:
    race_entry = await get_or_404(session, RaceEntry, race_entry_id)

    updates = body.model_dump(exclude_unset=True)
    if updates:
        for field, value in updates.items():
            setattr(race_entry, field, value)
        race_entry.updated_by = user.id
        session.add(race_entry)
        await session.commit()
    return race_entry


@router.delete("/race-entries/{race_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_race_entry(
    race_entry_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    race_entry = await get_or_404(session, RaceEntry, race_entry_id)

    await session.delete(race_entry)
    await session.commit()
