from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Event, EventRead, User, Venue

router = APIRouter()


async def _validate_venue_id(venue_id: int | None, session: AsyncSession) -> None:
    if venue_id is None:
        return
    venue = (await session.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="venue_id does not reference an existing Venue",
        )


class EventCreate(SQLModel):
    name: str
    description: str
    venue_id: int | None = None
    format: str
    start_date: date
    end_date: date
    image_url: str | None = None


@router.post("/events", response_model=EventRead)
async def create_event(
    body: EventCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Event:
    await _validate_venue_id(body.venue_id, session)

    event = Event(
        name=body.name,
        description=body.description,
        venue_id=body.venue_id,
        format=body.format,
        start_date=body.start_date,
        end_date=body.end_date,
        image_url=body.image_url,
        created_by=user.id,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.get("/events/{event_id}", response_model=EventRead)
async def get_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Event:
    event = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.get("/events", response_model=list[EventRead])
async def list_events(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Event]:
    return list((await session.execute(select(Event))).scalars().all())


class EventUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    venue_id: int | None = None
    format: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    image_url: str | None = None


@router.patch("/events/{event_id}", response_model=EventRead)
async def update_event(
    event_id: int,
    body: EventUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Event:
    event = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    updates = body.model_dump(exclude_unset=True)
    if "venue_id" in updates:
        await _validate_venue_id(updates["venue_id"], session)

    for field, value in updates.items():
        setattr(event, field, value)
    event.updated_by = user.id

    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    event = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    await session.delete(event)
    await session.commit()
