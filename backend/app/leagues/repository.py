from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.leagues.models import League, LeagueInvite, LeagueUser
from app.models import User


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


async def list_active_members(
    session: AsyncSession, league_id: int
) -> list[tuple[LeagueUser, User]]:
    """Every live membership of a league, paired with the member's User row.

    An inner join, so app/soft_delete.py's global `deleted_at IS NULL` filter applies to
    both entities -- a member who left (soft-deleted LeagueUser) and a soft-deleted user
    both drop out, which is the behavior standings wants."""
    return list(
        (
            await session.execute(
                select(LeagueUser, User)
                .join(User, User.id == LeagueUser.user_id)
                .where(LeagueUser.league_id == league_id)
            )
        ).all()
    )
