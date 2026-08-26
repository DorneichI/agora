from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import require_username
from app.crud_helpers import assert_not_referenced, get_or_404, validate_fk_exists
from app.db import get_session
from app.deps import require_admin
from app.gameplay import repository
from app.gameplay.models import (
    Event,
    EventRead,
    Race,
    RaceEntry,
    RaceEntryRead,
    RaceRead,
    Team,
    TeamRead,
    Venue,
    VenueRead,
)
from app.models import User

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
    return await repository.list_teams(session)


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


class VenueCreate(SQLModel):
    name: str
    location: str
    image_url: str | None = None


@router.post("/venues", response_model=VenueRead)
async def create_venue(
    body: VenueCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    venue = Venue(
        name=body.name,
        location=body.location,
        image_url=body.image_url,
        created_by=user.id,
    )
    session.add(venue)
    await session.commit()
    return venue


@router.get("/venues/{venue_id}", response_model=VenueRead)
async def get_venue(
    venue_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    return await get_or_404(session, Venue, venue_id)


@router.get("/venues", response_model=list[VenueRead])
async def list_venues(
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[Venue]:
    return await repository.list_venues(session)


class VenueUpdate(SQLModel):
    name: str | None = None
    location: str | None = None
    image_url: str | None = None


@router.patch("/venues/{venue_id}", response_model=VenueRead)
async def update_venue(
    venue_id: int,
    body: VenueUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    venue = await get_or_404(session, Venue, venue_id)

    updates = body.model_dump(exclude_unset=True)
    if updates:
        for field, value in updates.items():
            setattr(venue, field, value)
        venue.updated_by = user.id
        session.add(venue)
        await session.commit()
    return venue


@router.delete("/venues/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue(
    venue_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    venue = await get_or_404(session, Venue, venue_id)
    await assert_not_referenced(session, Event, "venue_id", venue_id, "Venue")

    await session.delete(venue)
    await session.commit()


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
    return await repository.list_events(session)


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
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[Race]:
    return await repository.list_races(session)


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
    return await repository.list_race_entries(session)


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
