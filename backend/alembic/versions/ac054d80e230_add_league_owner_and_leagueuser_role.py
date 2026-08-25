"""add league owner and leagueuser role

Revision ID: ac054d80e230
Revises: b09ef87865dc
Create Date: 2026-08-25 14:50:01.223167

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac054d80e230"
down_revision: str | Sequence[str] | None = "b09ef87865dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("league", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.execute('UPDATE "league" SET owner_id = created_by')
    op.alter_column("league", "owner_id", nullable=False)
    op.create_foreign_key("league_owner_id_fkey", "league", "user", ["owner_id"], ["id"])

    op.add_column(
        "leagueuser",
        sa.Column(
            "role",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="member",
        ),
    )
    op.execute(
        """
        UPDATE "leagueuser"
        SET role = 'admin'
        WHERE user_id = (
            SELECT owner_id FROM "league" WHERE league.id = leagueuser.league_id
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("league_owner_id_fkey", "league", type_="foreignkey")
    op.drop_column("league", "owner_id")
    op.drop_column("leagueuser", "role")
