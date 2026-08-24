from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class Race(SoftDeleteMixin, table=True):
    event_id: int = Field(foreign_key="event.id")
    boat_class: str = Field()
    level: str = Field()
    round: str | None = Field(default=None)
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")


class RaceRead(SQLModel):
    """Public shape of a Race, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    Race later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    event_id: int
    boat_class: str
    level: str
    round: str | None
    created_by: int
    updated_by: int | None
