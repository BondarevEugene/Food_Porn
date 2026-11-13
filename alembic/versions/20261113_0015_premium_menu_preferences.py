"""Premium menu preferences and cuisine selection.

Revision ID: 20261113_0015
Revises: 20261109_0014
"""
import sqlalchemy as sa

from alembic import op

revision = "20261113_0015"
down_revision = "20261109_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menus",
        sa.Column("selection_mode", sa.String(length=12), nullable=False,
                  server_default="manual"),
    )
    op.add_column(
        "menus", sa.Column("selected_cuisine", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "menus",
        sa.Column("servings", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "menus",
        sa.Column("menu_mood", sa.String(length=24), nullable=False,
                  server_default="romantic"),
    )
    op.add_column(
        "menus",
        sa.Column("include_drinks", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )
    op.add_column(
        "menus",
        sa.Column("include_dessert", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("menus", "include_dessert")
    op.drop_column("menus", "include_drinks")
    op.drop_column("menus", "menu_mood")
    op.drop_column("menus", "servings")
    op.drop_column("menus", "selected_cuisine")
    op.drop_column("menus", "selection_mode")
