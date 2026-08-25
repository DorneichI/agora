import re

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin

USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,20}$")


class User(SoftDeleteMixin, table=True):
    clerk_id: str = Field()
    email: str = Field()
    username: str | None = Field(default=None)
    role: str = Field(default="user")

    __table_args__ = (
        Index(
            "ix_user_clerk_id_active",
            "clerk_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_user_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_user_username_active",
            "username",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class UserRead(SQLModel):
    """Public shape of a User, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    User later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    clerk_id: str
    email: str
    username: str | None
    role: str
