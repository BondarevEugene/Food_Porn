"""Окремі платні замовлення відеоісторій.

Revision ID: 20261109_0013
Revises: 20261108_0012
"""

from alembic import op
import sqlalchemy as sa

revision = "20261109_0013"
down_revision = "20261108_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_story_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wallpaper_order_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UAH"),
        sa.Column("status", sa.String(30), nullable=False,
                  server_default="waiting_for_payment"),
        sa.Column("payment_reference", sa.String(150), nullable=True),
        sa.Column("payment_system", sa.String(50), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("music_mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("music_mood", sa.String(30), nullable=False,
                  server_default="cinematic"),
        sa.Column("ai_voice", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("music_track_id", sa.String(100), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["wallpaper_order_id"], ["wallpaper_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index(
        "ix_video_story_orders_wallpaper_order_id",
        "video_story_orders", ["wallpaper_order_id"],
    )
    op.create_index(
        "ix_video_story_orders_telegram_user_id",
        "video_story_orders", ["telegram_user_id"],
    )
    op.create_index(
        "ix_video_story_orders_status",
        "video_story_orders", ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_story_orders_status", table_name="video_story_orders")
    op.drop_index(
        "ix_video_story_orders_telegram_user_id",
        table_name="video_story_orders",
    )
    op.drop_index(
        "ix_video_story_orders_wallpaper_order_id",
        table_name="video_story_orders",
    )
    op.drop_table("video_story_orders")
