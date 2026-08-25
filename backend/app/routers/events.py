from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.crud_helpers import assert_not_referenced, get_or_404, validate_fk_exists
from app.db import get_session
from app.deps import require_admin, require_username
from app.models import Event, EventRead, Race, User, Venue

router = APIRouter()


async def _validate_venue_id(venue_id: int | None, session: AsyncSession) -> None:
    if venue_id is None:
        return
    await validate_fk_exists(session, Venue, venue_id, "venue_id")


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must not be after end_date",
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
    _validate_date_range(body.start_date, body.end_date)

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
    return event


@router.get("/events/{event_id}", response_model=EventRead)
async def get_event(
    event_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Event:
    return await get_or_404(session, Event, event_id)


@router.get("/events", response_model=list[EventRead])
async def list_events(
    user: User = Depends(require_username),
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
    event = await get_or_404(session, Event, event_id)

    updates = body.model_dump(exclude_unset=True)
    if "venue_id" in updates:
        await _validate_venue_id(updates["venue_id"], session)
    if "start_date" in updates or "end_date" in updates:
        effective_start = updates.get("start_date", event.start_date)
        effective_end = updates.get("end_date", event.end_date)
        _validate_date_range(effective_start, effective_end)

    if updates:
        for field, value in updates.items():
            setattr(event, field, value)
        event.updated_by = user.id
        session.add(event)
        await session.commit()
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    event = await get_or_404(session, Event, event_id)
    await assert_not_referenced(session, Race, "event_id", event_id, "Event")

    await session.delete(event)
    await session.commit()
