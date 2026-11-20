"""Persist the Telegram receipt for a delivered Little Legend PDF.

Revision ID: 20261120_0030
Revises: 20261120_0029
"""
import sqlalchemy as sa

from alembic import op

revision = "20261120_0030"
down_revision = "20261120_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_ll_fulfillment_telegram_message_id",
        "little_legend_fulfillment_jobs",
        "telegram_message_id IS NULL OR telegram_message_id > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ll_fulfillment_telegram_message_id",
        "little_legend_fulfillment_jobs",
        type_="check",
    )
    op.drop_column("little_legend_fulfillment_jobs", "telegram_message_id")
