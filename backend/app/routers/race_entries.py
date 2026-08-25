from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Race, RaceEntry, RaceEntryRead, Team, User

router = APIRouter()

RaceEntryStatus = Literal["finished", "dnf", "dns", "dq"]


async def _validate_race_id(race_id: int, session: AsyncSession) -> None:
    race = (await session.execute(select(Race).where(Race.id == race_id))).scalar_one_or_none()
    if race is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="race_id does not reference an existing Race",
        )


async def _validate_team_id(team_id: int, session: AsyncSession) -> None:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="team_id does not reference an existing Team",
        )


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
    await session.refresh(race_entry)
    return race_entry


@router.get("/race-entries/{race_entry_id}", response_model=RaceEntryRead)
async def get_race_entry(
    race_entry_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RaceEntry:
    race_entry = (
        await session.execute(select(RaceEntry).where(RaceEntry.id == race_entry_id))
    ).scalar_one_or_none()
    if race_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RaceEntry not found")
    return race_entry


@router.get("/race-entries", response_model=list[RaceEntryRead])
async def list_race_entries(
    user: User = Depends(get_current_user),
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
    race_entry = (
        await session.execute(select(RaceEntry).where(RaceEntry.id == race_entry_id))
    ).scalar_one_or_none()
    if race_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RaceEntry not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(race_entry, field, value)
    race_entry.updated_by = user.id

    session.add(race_entry)
    await session.commit()
    await session.refresh(race_entry)
    return race_entry


@router.delete("/race-entries/{race_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_race_entry(
    race_entry_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    race_entry = (
        await session.execute(select(RaceEntry).where(RaceEntry.id == race_entry_id))
    ).scalar_one_or_none()
    if race_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RaceEntry not found")

    await session.delete(race_entry)
    await session.commit()
