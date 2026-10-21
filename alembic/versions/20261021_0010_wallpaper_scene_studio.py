"""
==========================================================
FOOD_PORN

Module: Wallpaper Scene Studio Migration
Layer: Database Migration

Revision ID: 20261021_0010
Revises: 20261020_0009
==========================================================
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261021_0010"
down_revision: str | None = "20261020_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wallpaper_orders", sa.Column("goals", sa.JSON(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("scene_prompts", sa.JSON(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("scene_assignments", sa.JSON(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("source_photo_paths", sa.JSON(), nullable=True))
    op.add_column(
        "wallpaper_orders",
        sa.Column("locked_scene_indexes", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.add_column(
        "wallpaper_orders",
        sa.Column("visual_style", sa.String(length=20), server_default="dark", nullable=False),
    )
    op.add_column("wallpaper_orders", sa.Column("final_phrase", sa.String(length=500), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("original_mobile_path", sa.Text(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("original_desktop_path", sa.Text(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("raw_mobile_path", sa.Text(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("raw_desktop_path", sa.Text(), nullable=True))
    op.execute(
        "UPDATE wallpaper_orders SET original_mobile_path = mobile_path, "
        "original_desktop_path = desktop_path"
    )

    op.create_table(
        "wallpaper_scene_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("scene_asset_path", sa.Text(), nullable=False),
        sa.Column("edit_mode", sa.String(length=20), nullable=False),
        sa.Column("instruction", sa.String(length=500), nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("ai_cost_usd", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["wallpaper_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id", "scene_index", "version_number",
            name="uq_wallpaper_scene_version_number",
        ),
    )
    op.create_index("ix_wallpaper_scene_versions_order_id", "wallpaper_scene_versions", ["order_id"])
    op.create_index("ix_wallpaper_scene_versions_scene_index", "wallpaper_scene_versions", ["scene_index"])
    op.create_index("ix_wallpaper_scene_versions_is_selected", "wallpaper_scene_versions", ["is_selected"])

    op.create_table(
        "wallpaper_exports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("source_revision", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["wallpaper_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "kind", name="uq_wallpaper_export_kind"),
    )
    op.create_index("ix_wallpaper_exports_order_id", "wallpaper_exports", ["order_id"])
    op.create_index("ix_wallpaper_exports_kind", "wallpaper_exports", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_wallpaper_exports_kind", table_name="wallpaper_exports")
    op.drop_index("ix_wallpaper_exports_order_id", table_name="wallpaper_exports")
    op.drop_table("wallpaper_exports")
    op.drop_index("ix_wallpaper_scene_versions_is_selected", table_name="wallpaper_scene_versions")
    op.drop_index("ix_wallpaper_scene_versions_scene_index", table_name="wallpaper_scene_versions")
    op.drop_index("ix_wallpaper_scene_versions_order_id", table_name="wallpaper_scene_versions")
    op.drop_table("wallpaper_scene_versions")
    for column in (
        "raw_desktop_path", "raw_mobile_path", "original_desktop_path", "original_mobile_path",
        "final_phrase", "visual_style", "locked_scene_indexes", "source_photo_paths",
        "scene_assignments", "scene_prompts", "goals",
    ):
        op.drop_column("wallpaper_orders", column)
