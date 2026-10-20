"""
==========================================================
FOOD_PORN

Module: WayForPay Payments Migration
Layer: Database Migration

Revision ID: 20261020_0009
Revises: 20261019_0008
Create Date: 2026-10-20
==========================================================
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0009"
down_revision: str | None = "20261019_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wayforpay_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product", sa.String(length=20), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False),
        sa.Column("order_reference", sa.String(length=100), nullable=False),
        sa.Column("checkout_token", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=250), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("transaction_status", sa.String(length=40), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=120), nullable=True),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("test_mode", sa.Boolean(), nullable=False),
        sa.Column("grants_entitlement", sa.Boolean(), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkout_token", name="uq_wayforpay_checkout_token"),
        sa.UniqueConstraint("order_reference", name="uq_wayforpay_order_reference"),
    )
    op.create_index("ix_wayforpay_payments_paid_at", "wayforpay_payments", ["paid_at"])
    op.create_index("ix_wayforpay_payments_product", "wayforpay_payments", ["product"])
    op.create_index("ix_wayforpay_payments_reference_id", "wayforpay_payments", ["reference_id"])
    op.create_index("ix_wayforpay_payments_status", "wayforpay_payments", ["status"])
    op.create_index("ix_wayforpay_payments_telegram_user_id", "wayforpay_payments", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_wayforpay_payments_telegram_user_id", table_name="wayforpay_payments")
    op.drop_index("ix_wayforpay_payments_status", table_name="wayforpay_payments")
    op.drop_index("ix_wayforpay_payments_reference_id", table_name="wayforpay_payments")
    op.drop_index("ix_wayforpay_payments_product", table_name="wayforpay_payments")
    op.drop_index("ix_wayforpay_payments_paid_at", table_name="wayforpay_payments")
    op.drop_table("wayforpay_payments")
