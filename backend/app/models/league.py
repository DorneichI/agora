from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class League(SoftDeleteMixin, table=True):
    name: str = Field()
    created_by: int = Field(foreign_key="user.id")
    owner_id: int = Field(foreign_key="user.id")


class LeagueUser(SoftDeleteMixin, table=True):
    league_id: int = Field(foreign_key="league.id")
    user_id: int = Field(foreign_key="user.id")
    role: str = Field(default="member")

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
    id: int
    name: str
    created_by: int
    owner_id: int


class LeagueUserRead(SQLModel):
    id: int
    league_id: int
    user_id: int
    role: str
