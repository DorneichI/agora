import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import require_username
from app.leagues.deps import require_league_admin, require_league_member, require_league_owner
from app.leagues.models import (
    League,
    LeagueInvite,
    LeagueInviteRead,
    LeagueRead,
    LeagueUser,
    LeagueUserRead,
)
from app.leagues.repository import (
    get_active_membership,
    get_invite_by_code,
    get_league_by_id,
    get_membership_including_deleted,
)
from app.models import User

router = APIRouter()

INVITE_LIFETIME = timedelta(days=7)

# Postgres SQLSTATE for a unique-constraint violation.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


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


class InviteCreate(SQLModel):
    target_username: str | None = None


def _is_invite_code_collision(exc: IntegrityError) -> bool:
    """Distinguish "the generated code collided with the partial unique index" from any
    other IntegrityError (e.g. a bad FK) so the retry loop below only retries the case it
    actually knows how to recover from.

    SQLAlchemy's asyncpg dialect wraps the driver error and re-raises it with
    `raise translated_error from error`, so the original `asyncpg.exceptions.
    UniqueViolationError` -- which carries the Postgres diagnostic fields `sqlstate` and
    `constraint_name` -- is available via `exc.orig.__cause__`. `exc.orig` itself (SQLAlchemy's
    thin DBAPI wrapper) only exposes `sqlstate`/`pgcode`, not `constraint_name`. Verified
    empirically against a real Postgres/asyncpg unique-violation.
    """
    cause = getattr(exc.orig, "__cause__", None)
    return (
        getattr(cause, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE
        and getattr(cause, "constraint_name", None) == "ix_leagueinvite_code_active"
    )


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
    league = await get_league_by_id(session, league_id)
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
    league = await get_league_by_id(session, league_id)
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
        membership = await get_active_membership(session, league_id, user.id)
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
    league = await get_league_by_id(session, league_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    if league.visibility != "public":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This league is not public"
        )

    membership = await get_membership_including_deleted(session, league_id, user.id)

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
    league = await get_league_by_id(session, league_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    if league.owner_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The owner must transfer ownership before leaving the league",
        )

    membership = await get_active_membership(session, league_id, user.id)

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
    membership = await get_active_membership(session, league_id, user_id)
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
    membership = await get_active_membership(session, league_id, user_id)
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

    membership = await get_active_membership(session, league_id, user_id)
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

    membership = await get_active_membership(session, league_id, body.new_owner_id)
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


@router.post("/leagues/{league_id}/invites", response_model=LeagueInviteRead)
async def create_invite(
    league_id: int,
    body: InviteCreate,
    league: League = Depends(require_league_member),
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> LeagueInvite:
    is_owner = user.id == league.owner_id
    if league.invite_policy == "owner_only" and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the league owner can create invites",
        )
    if league.invite_policy == "admins_only" and not is_owner:
        membership = await get_active_membership(session, league_id, user.id)
        if membership is None or membership.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="League admin privileges required to create invites",
            )

    if league.visibility == "public":
        if body.target_username is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="target_username must be omitted for a public league invite",
            )
        target_user_id = None
    else:
        if body.target_username is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="target_username is required for a private league invite",
            )
        target_user = (
            await session.execute(select(User).where(User.username == body.target_username))
        ).scalar_one_or_none()
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user found with that username",
            )
        target_user_id = target_user.id

    # Captured once, before the loop: a collision's rollback (below) expires every ORM
    # object tracked by this request's session, including `user`. Re-reading `user.id`
    # inside the loop after that would be a synchronous lazy-load on an expired attribute,
    # which raises MissingGreenlet outside of an awaited call. Reusing this plain int
    # instead sidesteps that -- it needs no DB round trip and doesn't change between
    # attempts anyway.
    created_by = user.id

    for _attempt in range(5):
        invite = LeagueInvite(
            league_id=league_id,
            code=secrets.token_urlsafe(32),
            created_by=created_by,
            target_user_id=target_user_id,
            expires_at=datetime.now(UTC) + INVITE_LIFETIME,
        )
        session.add(invite)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if _is_invite_code_collision(exc):
                continue
            raise
        await session.refresh(invite)
        return invite

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate a unique invite code",
    )


@router.post("/invites/{code}/redeem", status_code=status.HTTP_204_NO_CONTENT)
async def redeem_invite(
    code: str,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> None:
    invite = await get_invite_by_code(session, code)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    now = datetime.now(UTC)
    is_targeted = invite.target_user_id is not None

    league_no_longer_public = False
    if not is_targeted:
        league = await get_league_by_id(session, invite.league_id)
        league_no_longer_public = league is None or league.visibility != "public"

    invite_is_dead = invite.revoked_at is not None or now > invite.expires_at
    invite_already_redeemed = is_targeted and invite.redeemed_at is not None
    if invite_is_dead or invite_already_redeemed or league_no_longer_public:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="This invite is no longer valid"
        )
    if is_targeted and invite.target_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This invite is for a different user"
        )

    if is_targeted:
        result = await session.execute(
            update(LeagueInvite)
            .where(
                LeagueInvite.id == invite.id,
                LeagueInvite.redeemed_at.is_(None),
                LeagueInvite.revoked_at.is_(None),
            )
            .values(redeemed_at=now)
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail="This invite is no longer valid"
            )

    membership = await get_membership_including_deleted(session, invite.league_id, user.id)

    if membership is None:
        session.add(LeagueUser(league_id=invite.league_id, user_id=user.id))
    elif membership.deleted_at is not None:
        membership.deleted_at = None
        session.add(membership)

    await session.commit()


@router.delete("/invites/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    code: str,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> None:
    invite = await get_invite_by_code(session, code)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    # The creator can always revoke their own invite, with no membership check -- that
    # permission is tied to having created it, not to still being in the league (deliberate,
    # see docs/superpowers/specs/2026-08-26-league-invite-codes-design.md). Anyone else must be
    # a *current* active admin/owner of the invite's league.
    if invite.created_by != user.id:
        membership = await get_active_membership(session, invite.league_id, user.id)
        if membership is None or membership.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to revoke this invite",
            )

    now = datetime.now(UTC)
    if invite.redeemed_at is not None or invite.revoked_at is not None or now > invite.expires_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing left to revoke")

    invite.revoked_at = now
    session.add(invite)
    await session.commit()
