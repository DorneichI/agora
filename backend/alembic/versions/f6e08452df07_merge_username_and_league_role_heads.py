"""merge username and league-role heads

Revision ID: f6e08452df07
Revises: 2b746ba9f390, ac054d80e230
Create Date: 2026-08-25 18:32:01.076875

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f6e08452df07"
down_revision: str | Sequence[str] | None = ("2b746ba9f390", "ac054d80e230")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
