from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class User(SoftDeleteMixin, table=True):
    clerk_id: str = Field()
    email: str = Field()
    display_name: str = Field()

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
    display_name: str
