from datetime import date

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class Team(SoftDeleteMixin, table=True):
    name: str = Field()
    school: str = Field()
    mascot: str = Field()
    image_url: str | None = Field(default=None)
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")


class TeamRead(SQLModel):
    """Public shape of a Team, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    Team later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    name: str
    school: str
    mascot: str
    image_url: str | None
    created_by: int
    updated_by: int | None


class Venue(SoftDeleteMixin, table=True):
    name: str = Field()
    location: str = Field()
    image_url: str | None = Field(default=None)
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")


class VenueRead(SQLModel):
    """Public shape of a Venue, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    Venue later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    name: str
    location: str
    image_url: str | None
    created_by: int
    updated_by: int | None


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


class Race(SoftDeleteMixin, table=True):
    name: str = Field()
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
    name: str
    event_id: int
    boat_class: str
    level: str
    round: str | None
    created_by: int
    updated_by: int | None


class RaceEntry(SoftDeleteMixin, table=True):
    race_id: int = Field(foreign_key="race.id")
    team_id: int = Field(foreign_key="team.id")
    level: str = Field()
    time: float | None = Field(default=None)
    status: str = Field(default="dns")
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")

    __table_args__ = (
        Index(
            "ix_raceentry_race_id_team_id_active",
            "race_id",
            "team_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class RaceEntryRead(SQLModel):
    """Public shape of a RaceEntry, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    RaceEntry later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    race_id: int
    team_id: int
    level: str
    time: float | None
    status: str
    created_by: int
    updated_by: int | None
