from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


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
