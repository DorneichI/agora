"""add name to race

Revision ID: 3da704f08832
Revises: 96903d034666
Create Date: 2026-08-31 17:33:37.961126

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3da704f08832"
down_revision: str | Sequence[str] | None = "96903d034666"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("race", sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("race", "name")
