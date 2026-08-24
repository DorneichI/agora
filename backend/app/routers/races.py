from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, Race, RaceRead, User

router = APIRouter()


async def _validate_event_id(event_id: int, session: AsyncSession) -> None:
    event = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="event_id does not reference an existing Event",
        )


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
    await session.refresh(race)
    return race


@router.get("/races/{race_id}", response_model=RaceRead)
async def get_race(
    race_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Race:
    race = (await session.execute(select(Race).where(Race.id == race_id))).scalar_one_or_none()
    if race is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race not found")
    return race


@router.get("/races", response_model=list[RaceRead])
async def list_races(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Race]:
    return list((await session.execute(select(Race))).scalars().all())


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
    race = (await session.execute(select(Race).where(Race.id == race_id))).scalar_one_or_none()
    if race is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(race, field, value)
    race.updated_by = user.id

    session.add(race)
    await session.commit()
    await session.refresh(race)
    return race


@router.delete("/races/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_race(
    race_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    race = (await session.execute(select(Race).where(Race.id == race_id))).scalar_one_or_none()
    if race is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race not found")

    await session.delete(race)
    await session.commit()
