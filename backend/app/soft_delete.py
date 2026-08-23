from datetime import UTC, datetime

from sqlalchemy import DateTime, event, inspect, true
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session, with_loader_criteria
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SoftDeleteMixin(SQLModel):
    """Adds id/created_at/updated_at/deleted_at to a table, plus soft-delete behavior
    via the events registered below."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": _utcnow},
    )
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


@event.listens_for(Session, "do_orm_execute")
def _exclude_soft_deleted(execute_state):
    if (
        execute_state.is_delete
        and not execute_state.execution_options.get("include_deleted", False)
        and any(issubclass(mapper.class_, SoftDeleteMixin) for mapper in execute_state.all_mappers)
    ):
        # A Core-style bulk `session.execute(delete(Model).where(...))` bypasses both this
        # event's SELECT/UPDATE scoping and the before_flush rewrite below (which only
        # intercepts per-instance `session.delete(obj)`) -- it would otherwise issue a
        # real, permanent SQL DELETE against a soft-deletable table. Forbid it outright
        # rather than silently hard-deleting.
        raise InvalidRequestError(
            "Bulk delete via session.execute(delete(...)) is not supported for "
            "soft-deletable tables: it would issue a real, permanent SQL DELETE, "
            "bypassing the soft-delete mixin. Delete instances individually via "
            "session.delete(obj) instead, which is rewritten into a soft delete."
        )

    if (
        (execute_state.is_select or execute_state.is_update)
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                # SQLAlchemy calls this once speculatively during lambda-closure analysis with
                # a wrapper that forwards attribute access to SoftDeleteMixin itself (which,
                # being a plain unmapped SQLModel/Pydantic mixin, has no real `deleted_at`
                # attribute) before calling it again per concrete mapped subclass, where
                # `cls.deleted_at` does resolve to a real column. The hasattr guard makes the
                # speculative call a no-op instead of raising AttributeError.
                lambda cls: cls.deleted_at.is_(None) if hasattr(cls, "deleted_at") else true(),
                include_aliases=True,
            )
        )


@event.listens_for(Session, "before_flush")
def _rewrite_delete_as_soft_delete(session, flush_context, instances):
    for obj in list(session.deleted):
        if isinstance(obj, SoftDeleteMixin):
            # No public API cancels a pending session.delete(); this mirrors what
            # SQLAlchemy's own rollback path does internally. Not a documented API —
            # if a future SQLAlchemy upgrade changes this internal, this file's tests
            # will catch it immediately.
            session._deleted.pop(inspect(obj), None)
            obj.deleted_at = _utcnow()
