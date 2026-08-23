from sqlalchemy import Index, text
from sqlmodel import Field

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
