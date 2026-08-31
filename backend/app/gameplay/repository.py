from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.gameplay.models import Event, Race, RaceEntry, Team, Venue


async def list_teams(session: AsyncSession) -> list[Team]:
    return list((await session.execute(select(Team))).scalars().all())


async def list_venues(session: AsyncSession) -> list[Venue]:
    return list((await session.execute(select(Venue))).scalars().all())


async def list_events(session: AsyncSession) -> list[Event]:
    return list((await session.execute(select(Event))).scalars().all())


async def list_races(session: AsyncSession, event_id: int | None = None) -> list[Race]:
    statement = select(Race)
    if event_id is not None:
        statement = statement.where(Race.event_id == event_id)
    return list((await session.execute(statement)).scalars().all())


async def list_race_entries(session: AsyncSession, race_id: int | None = None) -> list[RaceEntry]:
    statement = select(RaceEntry)
    if race_id is not None:
        statement = statement.where(RaceEntry.race_id == race_id)
    return list((await session.execute(statement)).scalars().all())
