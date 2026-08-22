from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SoftDeleteMixin(SQLModel):
    """Adds id/created_at/updated_at/deleted_at to a table, plus soft-delete behavior
    via the events registered below."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    deleted_at: datetime | None = Field(default=None)
