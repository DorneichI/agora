from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.gameplay.models import Event, Race, RaceEntry, Team, Venue


async def list_teams(session: AsyncSession) -> list[Team]:
    return list((await session.execute(select(Team))).scalars().all())


async def list_venues(session: AsyncSession) -> list[Venue]:
    return list((await session.execute(select(Venue))).scalars().all())


async def list_events(session: AsyncSession) -> list[Event]:
    return list((await session.execute(select(Event))).scalars().all())


async def list_races(session: AsyncSession) -> list[Race]:
    return list((await session.execute(select(Race))).scalars().all())


async def list_race_entries(session: AsyncSession) -> list[RaceEntry]:
    return list((await session.execute(select(RaceEntry))).scalars().all())
