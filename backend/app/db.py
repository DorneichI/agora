import os

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

engine: AsyncEngine = create_async_engine(os.environ["DATABASE_URL"])
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
