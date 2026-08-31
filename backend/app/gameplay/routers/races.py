from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import require_username
from app.crud_helpers import assert_not_referenced, get_or_404, validate_fk_exists
from app.db import get_session
from app.deps import require_admin
from app.gameplay import repository
from app.gameplay.models import Event, Race, RaceEntry, RaceRead
from app.gameplay.routers._shared import _reject_null_updates
from app.models import User

router = APIRouter()


async def _validate_event_id(event_id: int, session: AsyncSession) -> None:
    await validate_fk_exists(session, Event, event_id, "event_id")


class RaceCreate(SQLModel):
    event_id: int
    boat_class: str
    level: str
    round: str | None = None


@router.post("/races", response_model=RaceRead)
async def create_race(
    body: RaceCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Race:
    await _validate_event_id(body.event_id, session)

    race = Race(
        event_id=body.event_id,
        boat_class=body.boat_class,
        level=body.level,
        round=body.round,
        created_by=user.id,
    )
    session.add(race)
    await session.commit()
    return race


@router.get("/races/{race_id}", response_model=RaceRead)
async def get_race(
    race_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Race:
    return await get_or_404(session, Race, race_id)


@router.get("/races", response_model=list[RaceRead])
async def list_races(
    event_id: int | None = None,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[Race]:
    return await repository.list_races(session, event_id=event_id)


class RaceUpdate(SQLModel):
    boat_class: str | None = None
    level: str | None = None
    round: str | None = None


@router.patch("/races/{race_id}", response_model=RaceRead)
async def update_race(
    race_id: int,
    body: RaceUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Race:
    race = await get_or_404(session, Race, race_id)

    updates = body.model_dump(exclude_unset=True)
    _reject_null_updates(updates, {"boat_class", "level"})
    if updates:
        for field, value in updates.items():
            setattr(race, field, value)
        race.updated_by = user.id
        session.add(race)
        await session.commit()
    return race


@router.delete("/races/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_race(
    race_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    race = await get_or_404(session, Race, race_id)
    await assert_not_referenced(session, RaceEntry, "race_id", race_id, "Race")

    await session.delete(race)
    await session.commit()
