from datetime import date

from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class Event(SoftDeleteMixin, table=True):
    name: str = Field()
    description: str = Field()
    venue_id: int | None = Field(default=None, foreign_key="venue.id")
    format: str = Field()
    start_date: date = Field()
    end_date: date = Field()
    image_url: str | None = Field(default=None)
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")


class EventRead(SQLModel):
    """Public shape of an Event, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    Event later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    name: str
    description: str
    venue_id: int | None
    format: str
    start_date: date
    end_date: date
    image_url: str | None
    created_by: int
    updated_by: int | None
