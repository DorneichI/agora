from datetime import datetime

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class League(SoftDeleteMixin, table=True):
    name: str = Field()
    created_by: int = Field(foreign_key="user.id")
    owner_id: int = Field(foreign_key="user.id")
    visibility: str = Field(default="private")
    invite_policy: str = Field(default="owner_only")
    settings_policy: str = Field(default="owner_only")


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


class LeagueInvite(SoftDeleteMixin, table=True):
    league_id: int = Field(foreign_key="league.id")
    code: str = Field()
    created_by: int = Field(foreign_key="user.id")
    target_user_id: int | None = Field(default=None, foreign_key="user.id")
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    redeemed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_leagueinvite_code_active",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class LeagueRead(SQLModel):
    id: int
    name: str
    created_by: int
    owner_id: int
    visibility: str
    invite_policy: str
    settings_policy: str


class LeagueUserRead(SQLModel):
    id: int
    league_id: int
    user_id: int
    role: str


class LeagueInviteRead(SQLModel):
    id: int
    league_id: int
    code: str
    created_by: int
    target_user_id: int | None
    expires_at: datetime
    redeemed_at: datetime | None
    revoked_at: datetime | None
