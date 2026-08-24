"""One-off script: promote an already-provisioned user to admin by email.

Usage (from backend/):
    uv run python -m scripts.promote_admin <email>

Must be run as a module (-m), not as a plain script path (`python scripts/promote_admin.py`) --
running it as a plain script path puts scripts/ (not backend/) at the front of sys.path, so the
`app` package can't be found. Running as a module also matches how tests import this file
(`from scripts.promote_admin import ...`), which is why scripts/__init__.py exists.

Only works if that email already has a User row (i.e. they've logged in via Clerk at least
once) -- this never creates a new User.
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db import async_session_factory
from app.models import User


class UserNotFoundError(Exception):
    pass


async def promote_to_admin(session: AsyncSession, email: str) -> User:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise UserNotFoundError(
            f"No user with email {email!r} found. This script only promotes an "
            "already-provisioned user -- have them log in at least once first."
        )

    user.role = "admin"
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _main(email: str) -> None:
    async with async_session_factory() as session:
        try:
            user = await promote_to_admin(session, email)
        except UserNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        print(f"Promoted {user.email!r} (id={user.id}) to admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python -m scripts.promote_admin <email>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(_main(sys.argv[1]))
