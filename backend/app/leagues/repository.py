from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.leagues.models import League, LeagueInvite, LeagueUser


async def get_league_by_id(session: AsyncSession, league_id: int) -> League | None:
    return (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()


async def get_active_membership(
    session: AsyncSession, league_id: int, user_id: int
) -> LeagueUser | None:
    return (
        await session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def get_membership_including_deleted(
    session: AsyncSession, league_id: int, user_id: int
) -> LeagueUser | None:
    return (
        await session.execute(
            select(LeagueUser)
            .where(LeagueUser.league_id == league_id, LeagueUser.user_id == user_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()


async def get_invite_by_code(session: AsyncSession, code: str) -> LeagueInvite | None:
    return (
        await session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one_or_none()
