import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_active_league_membership, require_league_member, require_username
from app.models import League, LeagueInvite, LeagueInviteRead, LeagueUser, User

router = APIRouter()

INVITE_LIFETIME = timedelta(days=7)

# Postgres SQLSTATE for a unique-constraint violation.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


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
        membership = await get_active_league_membership(session, league_id, user.id)
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
    invite = (
        await session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    now = datetime.now(UTC)
    is_targeted = invite.target_user_id is not None

    league_no_longer_public = False
    if not is_targeted:
        league = (
            await session.execute(select(League).where(League.id == invite.league_id))
        ).scalar_one_or_none()
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

    membership = (
        await session.execute(
            select(LeagueUser)
            .where(LeagueUser.league_id == invite.league_id, LeagueUser.user_id == user.id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

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
    invite = (
        await session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    if invite.created_by != user.id:
        membership = await get_active_league_membership(session, invite.league_id, user.id)
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
