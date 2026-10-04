"""Snapshot Star prices and persist owner-authorized delivery links.

Revision ID: 20260930_0004
Revises: 20260928_0003
"""
import sqlalchemy as sa

from alembic import op

revision = "20260930_0004"
down_revision = "20260928_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menus", sa.Column("stars_amount", sa.Integer(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("stars_amount", sa.Integer(), nullable=True))
    op.add_column("wallpaper_orders", sa.Column("payment_system", sa.String(50), nullable=True))
    op.create_table(
        "share_links",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_share_links_owner_telegram_id", "share_links", ["owner_telegram_id"])
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("recipient_email", sa.String(254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_deliveries")
    op.drop_index("ix_share_links_owner_telegram_id", table_name="share_links")
    op.drop_table("share_links")
    op.drop_column("wallpaper_orders", "payment_system")
    op.drop_column("wallpaper_orders", "stars_amount")
    op.drop_column("menus", "stars_amount")
