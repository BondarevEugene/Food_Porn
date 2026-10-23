"""
==========================================================
FOOD_PORN

Module: Costs, Channels and Payment Timestamps Migration
Layer: Database Migration
==========================================================

Revision ID: 20261016_0006
Revises: 20261015_0005
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261016_0006"
down_revision: str | None = "20261015_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("source_channel", sa.String(length=30), server_default="telegram", nullable=False),
    )
    op.add_column("customers", sa.Column("external_user_id", sa.String(length=150), nullable=True))
    op.create_index("ix_customers_source_channel", "customers", ["source_channel"], unique=False)
    op.create_index("ix_customers_external_user_id", "customers", ["external_user_id"], unique=False)

    op.add_column("menu_items", sa.Column("servings", sa.Integer(), nullable=True))
    op.add_column("menu_items", sa.Column("difficulty", sa.String(length=30), nullable=True))
    op.add_column("menu_items", sa.Column("equipment", sa.JSON(), nullable=True))
    op.add_column("menu_items", sa.Column("allergens", sa.JSON(), nullable=True))
    op.add_column("menu_items", sa.Column("substitutions", sa.JSON(), nullable=True))
    op.add_column("menu_items", sa.Column("shopping_items", sa.JSON(), nullable=True))

    op.add_column("menus", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "menus",
        sa.Column("source_channel", sa.String(length=30), server_default="telegram", nullable=False),
    )
    op.create_index("ix_menus_paid_at", "menus", ["paid_at"], unique=False)
    op.create_index("ix_menus_source_channel", "menus", ["source_channel"], unique=False)
    op.execute("UPDATE menus SET paid_at = updated_at WHERE is_paid = true AND paid_at IS NULL")

    op.add_column(
        "wallpaper_orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "wallpaper_orders",
        sa.Column("source_channel", sa.String(length=30), server_default="telegram", nullable=False),
    )
    op.create_index("ix_wallpaper_orders_paid_at", "wallpaper_orders", ["paid_at"], unique=False)
    op.create_index(
        "ix_wallpaper_orders_source_channel", "wallpaper_orders", ["source_channel"], unique=False
    )
    op.execute(
        "UPDATE wallpaper_orders SET paid_at = updated_at WHERE paid = true AND paid_at IS NULL"
    )

    op.add_column(
        "ai_generation_logs",
        sa.Column("provider", sa.String(length=30), server_default="openai", nullable=False),
    )
    op.add_column(
        "ai_generation_logs",
        sa.Column("operation", sa.String(length=50), server_default="unknown", nullable=False),
    )
    op.add_column("ai_generation_logs", sa.Column("product_type", sa.String(length=30)))
    op.add_column("ai_generation_logs", sa.Column("order_id", sa.String(length=100)))
    op.add_column("ai_generation_logs", sa.Column("request_id", sa.String(length=150)))
    op.add_column(
        "ai_generation_logs",
        sa.Column("cached_input_tokens", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_generation_logs",
        sa.Column("status", sa.String(length=30), server_default="success", nullable=False),
    )
    op.add_column(
        "ai_generation_logs",
        sa.Column("pricing_source", sa.String(length=30), server_default="estimate", nullable=False),
    )
    op.add_column("ai_generation_logs", sa.Column("details", sa.JSON()))
    for name in ("provider", "operation", "product_type", "order_id", "request_id"):
        op.create_index(f"ix_ai_generation_logs_{name}", "ai_generation_logs", [name], unique=False)

    op.create_table(
        "provider_costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_key", sa.String(length=64), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="usd", nullable=False),
        sa.Column("project_id", sa.String(length=100), nullable=True),
        sa.Column("line_item", sa.String(length=150), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_key", name="uq_provider_costs_external_key"),
    )
    op.create_index("ix_provider_costs_provider", "provider_costs", ["provider"], unique=False)
    op.create_index(
        "ix_provider_costs_bucket_start", "provider_costs", ["bucket_start"], unique=False
    )
    op.create_index("ix_provider_costs_project_id", "provider_costs", ["project_id"], unique=False)

    op.create_table(
        "channel_contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("external_user_id", sa.String(length=150), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", "external_user_id", name="uq_channel_contact_identity"),
    )
    op.create_index("ix_channel_contacts_channel", "channel_contacts", ["channel"], unique=False)
    op.create_table(
        "channel_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("external_user_id", sa.String(length=150), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", "event_id", name="uq_channel_event_identity"),
    )
    op.create_index("ix_channel_events_channel", "channel_events", ["channel"], unique=False)
    op.create_index(
        "ix_channel_events_external_user_id", "channel_events", ["external_user_id"], unique=False
    )
    op.create_table(
        "scheduled_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False),
        sa.Column("recipient_email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=250), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_deliveries_owner_user_id", "scheduled_deliveries", ["owner_user_id"], unique=False)
    op.create_index("ix_scheduled_deliveries_send_at", "scheduled_deliveries", ["send_at"], unique=False)
    op.create_index("ix_scheduled_deliveries_status", "scheduled_deliveries", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduled_deliveries_status", table_name="scheduled_deliveries")
    op.drop_index("ix_scheduled_deliveries_send_at", table_name="scheduled_deliveries")
    op.drop_index("ix_scheduled_deliveries_owner_user_id", table_name="scheduled_deliveries")
    op.drop_table("scheduled_deliveries")
    op.drop_index("ix_channel_events_external_user_id", table_name="channel_events")
    op.drop_index("ix_channel_events_channel", table_name="channel_events")
    op.drop_table("channel_events")
    op.drop_index("ix_channel_contacts_channel", table_name="channel_contacts")
    op.drop_table("channel_contacts")
    op.drop_index("ix_provider_costs_project_id", table_name="provider_costs")
    op.drop_index("ix_provider_costs_bucket_start", table_name="provider_costs")
    op.drop_index("ix_provider_costs_provider", table_name="provider_costs")
    op.drop_table("provider_costs")

    for name in ("request_id", "order_id", "product_type", "operation", "provider"):
        op.drop_index(f"ix_ai_generation_logs_{name}", table_name="ai_generation_logs")
    for name in (
        "details",
        "pricing_source",
        "status",
        "cached_input_tokens",
        "request_id",
        "order_id",
        "product_type",
        "operation",
        "provider",
    ):
        op.drop_column("ai_generation_logs", name)

    op.drop_index("ix_wallpaper_orders_source_channel", table_name="wallpaper_orders")
    op.drop_index("ix_wallpaper_orders_paid_at", table_name="wallpaper_orders")
    op.drop_column("wallpaper_orders", "source_channel")
    op.drop_column("wallpaper_orders", "paid_at")
    op.drop_index("ix_menus_source_channel", table_name="menus")
    op.drop_index("ix_menus_paid_at", table_name="menus")
    op.drop_column("menus", "source_channel")
    op.drop_column("menus", "paid_at")
    op.drop_index("ix_customers_external_user_id", table_name="customers")
    op.drop_index("ix_customers_source_channel", table_name="customers")
    op.drop_column("customers", "external_user_id")
    op.drop_column("customers", "source_channel")
    for name in (
        "shopping_items",
        "substitutions",
        "allergens",
        "equipment",
        "difficulty",
        "servings",
    ):
        op.drop_column("menu_items", name)
