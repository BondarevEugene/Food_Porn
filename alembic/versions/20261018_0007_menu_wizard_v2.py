"""
==========================================================
FOOD_PORN

Module: Menu Wizard V2 Migration
Layer: Database Migration
==========================================================

Revision ID: 20261018_0007
Revises: 20261016_0006
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261018_0007"
down_revision: str | None = "20261016_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("menus", sa.Column("meal_period", sa.String(length=20), nullable=True))
    op.add_column("menus", sa.Column("visual_style", sa.String(length=60), nullable=True))
    op.create_index("ix_menus_meal_period", "menus", ["meal_period"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_menus_meal_period", table_name="menus")
    op.drop_column("menus", "visual_style")
    op.drop_column("menus", "meal_period")
