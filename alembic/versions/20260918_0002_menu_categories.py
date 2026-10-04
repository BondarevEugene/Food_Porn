"""
==========================================================
FOOD_PORN

Module: Extended Menu Categories
Layer: Migration

Revision ID: 20260918_0002
Revises: 20260917_0001

Responsibilities:
    - Add appetizer and dessert PostgreSQL enum values
    - Preserve compatibility with existing menu records
==========================================================
"""

from alembic import op

revision = "20260918_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum values are stored by SQLAlchemy member name.
    op.execute("ALTER TYPE item_category_enum ADD VALUE IF NOT EXISTS 'APPETIZER'")
    op.execute("ALTER TYPE item_category_enum ADD VALUE IF NOT EXISTS 'DESSERT'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove enum members in place. The legacy values
    # are harmless, so downgrade intentionally preserves them.
    pass
