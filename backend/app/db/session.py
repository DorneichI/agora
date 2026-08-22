"""Async engine/session setup shared by the app and its tests.

`DATABASE_URL` (see root `.env.example`) must already be in the async-driver form
(`postgresql+asyncpg://...`) — the same value Alembic's `env.py` reads.
"""

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.environ["DATABASE_URL"]

engine: AsyncEngine = create_async_engine(DATABASE_URL)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
