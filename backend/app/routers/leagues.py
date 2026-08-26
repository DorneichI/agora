from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.auth.deps import require_username
from app.db import get_session
from app.deps import (
    get_active_league_membership,
    require_league_admin,
    require_league_owner,
)
from app.models import League, LeagueRead, LeagueUser, LeagueUserRead, User

router = APIRouter()


class LeagueCreate(SQLModel):
    name: str


class TransferOwnershipRequest(SQLModel):
    new_owner_id: int


LeagueVisibility = Literal["public", "private"]
InvitePolicy = Literal["anyone", "admins_only", "owner_only"]
SettingsPolicy = Literal["owner_only", "admins_only"]


class LeagueSettingsUpdate(SQLModel):
    visibility: LeagueVisibility | None = None
    invite_policy: InvitePolicy | None = None
    settings_policy: SettingsPolicy | None = None


@router.post("/leagues", response_model=LeagueRead)
async def create_league(
    body: LeagueCreate,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = League(name=body.name, created_by=user.id, owner_id=user.id)
    session.add(league)
    await session.flush()

    session.add(LeagueUser(league_id=league.id, user_id=user.id, role="admin"))
    await session.commit()
    await session.refresh(league)
    return league


@router.get("/leagues/{league_id}", response_model=LeagueRead)
async def get_league(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league


@router.patch("/leagues/{league_id}", response_model=LeagueRead)
async def update_league_settings(
    league_id: int,
    body: LeagueSettingsUpdate,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return league

    is_owner = user.id == league.owner_id

    if "settings_policy" in updates and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the league owner can change settings_policy",
        )

    if ("visibility" in updates or "invite_policy" in updates) and not is_owner:
        if league.settings_policy != "admins_only":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the league owner can change these settings",
            )
        membership = await get_active_league_membership(session, league_id, user.id)
        if membership is None or membership.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="League admin privileges required",
            )

    for field, value in updates.items():
        setattr(league, field, value)
    session.add(league)
    await session.commit()
    await session.refresh(league)
    return league


@router.post("/leagues/{league_id}/join", status_code=status.HTTP_204_NO_CONTENT)
async def join_league(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> None:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    if league.visibility != "public":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This league is not public"
        )

    membership = (
        await session.execute(
            select(LeagueUser)
            .where(LeagueUser.league_id == league_id, LeagueUser.user_id == user.id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

    if membership is None:
        session.add(LeagueUser(league_id=league_id, user_id=user.id))
        await session.commit()
    elif membership.deleted_at is not None:
        membership.deleted_at = None
        session.add(membership)
        await session.commit()


@router.post("/leagues/{league_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_league(
    league_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> None:
    league = (
        await session.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    if league.owner_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The owner must transfer ownership before leaving the league",
        )

    membership = (
        await session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == user.id
            )
        )
    ).scalar_one_or_none()

    if membership is not None:
        await session.delete(membership)
        await session.commit()


@router.post("/leagues/{league_id}/admins/{user_id}", response_model=LeagueUserRead)
async def promote_to_admin(
    league_id: int,
    user_id: int,
    league: League = Depends(require_league_admin),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> LeagueUser:
    membership = await get_active_league_membership(session, league_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if membership.role == "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already an admin")

    membership.role = "admin"
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


@router.delete("/leagues/{league_id}/admins/{user_id}", response_model=LeagueUserRead)
async def demote_admin(
    league_id: int,
    user_id: int,
    league: League = Depends(require_league_owner),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> LeagueUser:
    membership = await get_active_league_membership(session, league_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if user_id == league.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The owner cannot be demoted; transfer ownership instead",
        )
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is not an admin")

    membership.role = "member"
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


@router.delete("/leagues/{league_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kick_member(
    league_id: int,
    user_id: int,
    league: League = Depends(require_league_admin),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> None:
    if user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use POST /leagues/{league_id}/leave instead of kicking yourself",
        )

    membership = await get_active_league_membership(session, league_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if user_id == league.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The league owner cannot be kicked"
        )
    if membership.role == "admin" and user.id != league.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can kick an admin"
        )

    await session.delete(membership)
    await session.commit()


@router.post("/leagues/{league_id}/owner", response_model=LeagueRead)
async def transfer_ownership(
    league_id: int,
    body: TransferOwnershipRequest,
    league: League = Depends(require_league_owner),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> League:
    if body.new_owner_id == league.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already the owner"
        )

    membership = await get_active_league_membership(session, league_id, body.new_owner_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    league.owner_id = body.new_owner_id
    session.add(league)
    if membership.role != "admin":
        membership.role = "admin"
        session.add(membership)
    await session.commit()
    await session.refresh(league)
    return league
