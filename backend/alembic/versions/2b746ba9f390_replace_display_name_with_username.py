"""replace display_name with username

Revision ID: 2b746ba9f390
Revises: b09ef87865dc
Create Date: 2026-08-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b746ba9f390"
down_revision: str | Sequence[str] | None = "b09ef87865dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("user", sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(
        "ix_user_username_active",
        "user",
        ["username"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("user", "display_name")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "user",
        sa.Column(
            "display_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.drop_index(
        "ix_user_username_active", table_name="user", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_column("user", "username")
