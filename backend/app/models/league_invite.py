from datetime import datetime

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


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


class LeagueInviteRead(SQLModel):
    id: int
    league_id: int
    code: str
    created_by: int
    target_user_id: int | None
    expires_at: datetime
    redeemed_at: datetime | None
    revoked_at: datetime | None
