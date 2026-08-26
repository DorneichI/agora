"""add league visibility and policy columns

Revision ID: 9c41bae49314
Revises: f6e08452df07
Create Date: 2026-08-25 19:18:56.950083

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c41bae49314"
down_revision: str | Sequence[str] | None = "f6e08452df07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "league",
        sa.Column(
            "visibility",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="private",
        ),
    )
    op.add_column(
        "league",
        sa.Column(
            "invite_policy",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="owner_only",
        ),
    )
    op.add_column(
        "league",
        sa.Column(
            "settings_policy",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="owner_only",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("league", "settings_policy")
    op.drop_column("league", "invite_policy")
    op.drop_column("league", "visibility")
