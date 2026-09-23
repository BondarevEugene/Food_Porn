"""
==========================================================
FOOD_PORN

Module: Initial Database Schema
Layer: Migration

Revision ID: 20260917_0001
Revises: None

Responsibilities:
    - Create the initial customer and menu tables
    - Create generation, cache, and file persistence tables
    - Declare the first PostgreSQL enum types and indexes
==========================================================
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    language = sa.Enum("UK", "RU", "EN", name="language_enum")
    menu_language = sa.Enum("UK", "RU", "EN", name="menu_language_enum")
    menu_status = sa.Enum("DRAFT", "QUEUED", "GENERATING", "RENDERING", "COMPLETE", "FAILED", name="menu_status_enum")
    item_category = sa.Enum("MAIN", "SALAD", "DRINK", name="item_category_enum")
    generation_status = sa.Enum("PENDING", "PROCESSING", "DONE", "FAILED", name="generation_status_enum")
    file_kind = sa.Enum("PREVIEW_OUTSIDE", "PREVIEW_INSIDE", "PRINT_PDF", name="file_kind_enum")

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("phone", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("language", language, nullable=False),
        sa.Column("country", sa.String(120), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "menus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", menu_language, nullable=False),
        sa.Column("status", menu_status, nullable=False),
        sa.Column("title", sa.String(180), nullable=False, server_default=""),
        sa.Column("cover_photo_path", sa.Text()),
        sa.Column("spread_photo_path", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("menu_id", sa.Integer(), sa.ForeignKey("menus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", item_category, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("image_prompt", sa.Text()),
        sa.Column("image_path", sa.Text()),
        sa.Column("generation_status", generation_status, nullable=False),
        sa.Column("generation_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("menu_id", "category", "position", name="uq_menu_item_position"),
    )
    op.create_index("ix_menu_items_status", "menu_items", ["generation_status"])
    op.create_table(
        "generated_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("menu_id", sa.Integer(), sa.ForeignKey("menus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", file_kind, nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("menu_id", "kind", name="uq_generated_file_kind"),
    )
    op.create_table(
        "image_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("image_cache")
    op.drop_table("generated_files")
    op.drop_index("ix_menu_items_status", table_name="menu_items")
    op.drop_table("menu_items")
    op.drop_table("menus")
    op.drop_table("customers")
    for name in (
        "file_kind_enum",
        "generation_status_enum",
        "item_category_enum",
        "menu_status_enum",
        "menu_language_enum",
        "language_enum",
    ):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
