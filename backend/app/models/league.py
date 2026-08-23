from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class League(SoftDeleteMixin, table=True):
    name: str = Field()
    created_by: int = Field(foreign_key="user.id")


class LeagueUser(SoftDeleteMixin, table=True):
    league_id: int = Field(foreign_key="league.id")
    user_id: int = Field(foreign_key="user.id")

    __table_args__ = (
        Index(
            "ix_leagueuser_league_id_user_id_active",
            "league_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class LeagueRead(SQLModel):
    """Public shape of a League, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    League later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table."""

    id: int
    name: str
    created_by: int
