"""Generic soft-delete pattern: mixin + global SQLAlchemy session events.

See docs/architecture.md's "Soft delete" section for the full rationale. Summary:

- `SoftDeleteMixin` adds `id`, `created_at`, `updated_at`, `deleted_at` to any model.
- A `do_orm_execute` event transparently filters out soft-deleted rows from every SELECT
  against a `SoftDeleteMixin` model, unless the query opts in with
  `.execution_options(include_deleted=True)`.
- A `before_flush` event rewrites `session.delete(obj)` on a `SoftDeleteMixin` model into
  setting `obj.deleted_at` (an UPDATE) instead of issuing a real DELETE.
- Any unique constraint on a soft-deletable table must be a partial unique index scoped to
  `WHERE deleted_at IS NULL` -- see the mixin's docstring below.

Both events are registered globally (module import time) on `sqlalchemy.orm.Session`, the
sync session class. This also covers `AsyncSession`: SQLAlchemy's asyncio extension executes
ORM-level work (including flush and `do_orm_execute`) through the underlying sync `Session`
it wraps internally, so events registered here fire for async sessions too -- no separate
async-specific registration is needed.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SoftDeleteMixin(SQLModel):
    """Mixin providing soft-delete columns and semantics for a SQLModel table.

    Usage:

        class Widget(SoftDeleteMixin, table=True):
            name: str

    `deleted_at` is `NULL` for active rows and set to the deletion timestamp otherwise.
    Rows are never physically removed by this app's ORM usage: `session.delete(obj)` is
    rewritten (via the `before_flush` listener below) into setting `deleted_at`.

    Important: any unique constraint on a model using this mixin must be a **partial**
    unique index scoped to active rows, not a plain unique constraint -- otherwise a
    soft-deleted row permanently blocks reuse of that value (e.g. re-registering an email).
    Declare it in `__table_args__`, e.g.:

        __table_args__ = (
            Index(
                "ix_widget_name_active_unique",
                "name",
                unique=True,
                postgresql_where=text("deleted_at IS NULL"),
            ),
        )
    """

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"onupdate": _utcnow},
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


@event.listens_for(Session, "do_orm_execute")
def _exclude_soft_deleted(execute_state) -> None:
    """Add a `deleted_at IS NULL` filter to SELECTs against SoftDeleteMixin models.

    Skipped when the statement was run with `.execution_options(include_deleted=True)`.

    `with_loader_criteria` is applied per concrete mapped class rather than passing
    `SoftDeleteMixin` itself: SoftDeleteMixin is a `table=False` SQLModel mixin, so
    `SoftDeleteMixin.deleted_at` isn't a real SQLAlchemy-comparable attribute (only
    concrete `table=True` subclasses get one) -- attempting `cls.deleted_at` with `cls`
    bound to the mixin itself raises `AttributeError`.
    """
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        for mapper in execute_state.all_mappers:
            entity = mapper.class_
            if issubclass(entity, SoftDeleteMixin):
                execute_state.statement = execute_state.statement.options(
                    with_loader_criteria(
                        entity,
                        lambda cls: cls.deleted_at.is_(None),
                        include_aliases=True,
                    )
                )


@event.listens_for(Session, "before_flush")
def _rewrite_delete_as_soft_delete(session: Session, flush_context, instances) -> None:
    """Turn a pending `session.delete(obj)` on a SoftDeleteMixin model into an UPDATE.

    `session.deleted` is recomputed by `Session._flush()` right after this event fires, so
    removing the object from the pending-delete set here (and marking it dirty via the
    `deleted_at` attribute assignment) is enough to make the flush emit an UPDATE instead of
    a DELETE for it.
    """
    for obj in list(session.deleted):
        if isinstance(obj, SoftDeleteMixin) and obj.deleted_at is None:
            state = inspect(obj)
            session._deleted.pop(state, None)
            obj.deleted_at = _utcnow()
