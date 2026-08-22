"""Proves the generic soft-delete mechanism (mixin + events) from issue #15.

Uses a throwaway, test-only model (`Widget`) -- never a real domain model -- against a
real Postgres connection (see backend/CLAUDE.md for how to start one locally).
"""

import pytest
from sqlalchemy import Index, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, select

from app.db.session import async_session_maker, engine
from app.db.soft_delete import SoftDeleteMixin


class Widget(SoftDeleteMixin, table=True):
    """Throwaway model that exists only to exercise SoftDeleteMixin in tests."""

    name: str = Field(index=True)

    __table_args__ = (
        # Partial unique index scoped to active rows -- the rule from issue #15:
        # a plain unique constraint would let a soft-deleted row permanently block
        # reuse of the same value.
        Index(
            "ix_widget_name_active_unique",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


@pytest.fixture(autouse=True)
async def _widget_table():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all, tables=[Widget.__table__])
    yield
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all, tables=[Widget.__table__])
    # pytest-asyncio gives each test function its own event loop, but `engine`'s
    # asyncpg connection pool is created once at module import time and pinned to
    # whichever loop was running when its connections were opened. Dispose it after
    # every test so the next test's loop opens fresh connections instead of reusing
    # ones bound to a now-closed loop.
    await engine.dispose()


async def test_soft_deleted_row_excluded_from_normal_select():
    async with async_session_maker() as session:
        widget = Widget(name="alpha")
        session.add(widget)
        await session.commit()

        await session.delete(widget)
        await session.commit()

        result = await session.execute(select(Widget).where(Widget.name == "alpha"))
        assert result.scalars().all() == []


async def test_soft_deleted_row_returned_with_include_deleted():
    async with async_session_maker() as session:
        widget = Widget(name="beta")
        session.add(widget)
        await session.commit()
        widget_id = widget.id

        await session.delete(widget)
        await session.commit()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Widget).where(Widget.id == widget_id).execution_options(include_deleted=True)
        )
        found = result.scalars().one()
        assert found.id == widget_id
        assert found.deleted_at is not None


async def test_session_delete_sets_deleted_at_instead_of_removing_row():
    async with async_session_maker() as session:
        widget = Widget(name="gamma")
        session.add(widget)
        await session.commit()
        widget_id = widget.id

        await session.delete(widget)
        await session.commit()

        assert widget.deleted_at is not None

    # Confirm the row was never actually removed -- a plain SQL count still finds it.
    async with async_session_maker() as session:
        raw = await session.execute(
            text("SELECT deleted_at FROM widget WHERE id = :id"), {"id": widget_id}
        )
        row = raw.one()
        assert row[0] is not None


async def test_partial_unique_index_allows_reusing_value_after_soft_delete():
    async with async_session_maker() as session:
        first = Widget(name="delta")
        session.add(first)
        await session.commit()

        await session.delete(first)
        await session.commit()

        second = Widget(name="delta")
        session.add(second)
        await session.commit()  # would raise IntegrityError if the index weren't partial

        assert second.id is not None
        assert second.id != first.id


async def test_plain_active_duplicate_still_rejected_by_partial_index():
    async with async_session_maker() as session:
        session.add(Widget(name="epsilon"))
        await session.commit()

        session.add(Widget(name="epsilon"))
        with pytest.raises(IntegrityError):
            await session.commit()
