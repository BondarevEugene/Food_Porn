"""Store Telegram photo IDs for recoverable menu uploads.

Revision ID: 20261108_0011
Revises: 20261021_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261108_0011"
down_revision: str | None = "20261021_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("menus", sa.Column("cover_telegram_file_id", sa.Text(), nullable=True))
    op.add_column("menus", sa.Column("spread_telegram_file_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("menus", "spread_telegram_file_id")
    op.drop_column("menus", "cover_telegram_file_id")
