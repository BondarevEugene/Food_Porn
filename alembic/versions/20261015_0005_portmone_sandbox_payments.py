"""
==========================================================
FOOD_PORN

Module: Portmone Sandbox Payments Migration
Layer: Database Migration
==========================================================

Add isolated Portmone sandbox payment attempts.

Revision ID: 20261015_0005
Revises: aa913e48a33c
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261015_0005"
down_revision: str | None = "aa913e48a33c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portmone_sandbox_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product", sa.String(length=20), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payment_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portmone_sandbox_payments_telegram_user_id",
        "portmone_sandbox_payments",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portmone_sandbox_payments_telegram_user_id",
        table_name="portmone_sandbox_payments",
    )
    op.drop_table("portmone_sandbox_payments")
