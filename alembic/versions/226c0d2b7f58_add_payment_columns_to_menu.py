"""add_payment_columns_to_menu

Revision ID: 226c0d2b7f58
Revises: 20260918_0002
Create Date: 2026-09-24 23:43:46.302629
"""

from collections.abc import Sequence

from alembic import op

revision: str = '226c0d2b7f58'
down_revision: str | None = '20260918_0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Some older deployments used Base.metadata.create_all() before Alembic.
    op.execute("ALTER TABLE menus ADD COLUMN IF NOT EXISTS is_paid BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE menus ADD COLUMN IF NOT EXISTS payment_id VARCHAR(100)")
    op.execute("ALTER TABLE menus ADD COLUMN IF NOT EXISTS payment_system VARCHAR(50)")


def downgrade() -> None:
    # Откат миграции: удаление добавленных колонок
    op.drop_column('menus', 'payment_system')
    op.drop_column('menus', 'payment_id')
    op.drop_column('menus', 'is_paid')
