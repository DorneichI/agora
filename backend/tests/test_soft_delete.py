from datetime import UTC, datetime

import pytest
from sqlalchemy import Index, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, select

from app.soft_delete import SoftDeleteMixin


def _utcnow_for_test() -> datetime:
    return datetime.now(UTC)


class _MixinFieldsProbe(SoftDeleteMixin):
    name: str = Field()


def test_mixin_provides_id_timestamps_and_nullable_deleted_at():
    probe = _MixinFieldsProbe(name="widget")

    assert probe.id is None  # unset until inserted
    assert isinstance(probe.created_at, datetime)
    assert isinstance(probe.updated_at, datetime)
    assert probe.deleted_at is None


class _Widget(SoftDeleteMixin, table=True):
    __tablename__ = "test_soft_delete_widgets"
    name: str = Field()

    __table_args__ = (
        Index(
            "ix_test_soft_delete_widgets_name_active_unique",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


async def test_soft_deleted_row_excluded_unless_include_deleted(db_session):
    active = _Widget(name="active")
    deleted = _Widget(name="deleted")
    deleted.deleted_at = _utcnow_for_test()
    db_session.add_all([active, deleted])
    await db_session.commit()

    default_rows = (await db_session.execute(select(_Widget))).scalars().all()
    assert [w.name for w in default_rows] == ["active"]

    all_rows = (
        (await db_session.execute(select(_Widget).execution_options(include_deleted=True)))
        .scalars()
        .all()
    )
    assert sorted(w.name for w in all_rows) == ["active", "deleted"]


async def test_session_delete_soft_deletes_instead_of_removing_row(db_session):
    widget = _Widget(name="to-delete")
    db_session.add(widget)
    await db_session.commit()

    await db_session.delete(widget)
    await db_session.commit()

    remaining = (
        (await db_session.execute(select(_Widget).execution_options(include_deleted=True)))
        .scalars()
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].deleted_at is not None

    visible = (await db_session.execute(select(_Widget))).scalars().all()
    assert visible == []


async def test_partial_unique_index_allows_reusing_value_after_soft_delete(db_session):
    first = _Widget(name="delta")
    db_session.add(first)
    await db_session.commit()

    await db_session.delete(first)
    await db_session.commit()

    second = _Widget(name="delta")
    db_session.add(second)
    await db_session.commit()  # would raise IntegrityError if the index weren't partial

    assert second.id is not None
    assert second.id != first.id


async def test_plain_active_duplicate_still_rejected_by_partial_index(db_session):
    db_session.add(_Widget(name="epsilon"))
    await db_session.commit()

    db_session.add(_Widget(name="epsilon"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
