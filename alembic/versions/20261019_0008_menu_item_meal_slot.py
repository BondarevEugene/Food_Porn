"""
==========================================================
FOOD_PORN

Module: Menu Meal Slot Migration
Layer: Database Migration
==========================================================

Revision ID: 20261019_0008
Revises: 20261018_0007
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261019_0008"
down_revision: str | None = "20261018_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("menu_items", sa.Column("meal_slot", sa.String(length=20), nullable=True))
    op.create_index("ix_menu_items_meal_slot", "menu_items", ["meal_slot"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_menu_items_meal_slot", table_name="menu_items")
    op.drop_column("menu_items", "meal_slot")
