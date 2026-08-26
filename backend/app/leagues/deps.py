from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_username
from app.crud_helpers import get_or_404
from app.db import get_session
from app.leagues.models import League
from app.leagues.repository import get_active_membership
from app.models import User


async def require_league_member(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = await get_or_404(session, League, league_id)
    membership = await get_active_membership(session, league_id, user.id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="League membership required",
        )
    return league


async def require_league_admin(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = await get_or_404(session, League, league_id)
    membership = await get_active_membership(session, league_id, user.id)
    if membership is None or membership.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="League admin privileges required",
        )
    return league


async def require_league_owner(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = await get_or_404(session, League, league_id)
    if league.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="League owner privileges required",
        )
    return league
