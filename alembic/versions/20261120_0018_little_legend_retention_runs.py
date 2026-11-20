"""Aggregate-only retention operation history.

Revision ID: 20261120_0018
Revises: 20261118_0017
"""
import sqlalchemy as sa

from alembic import op

revision = "20261120_0018"
down_revision = "20261118_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_retention_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("codes", sa.JSON(), nullable=False),
        sa.Column("expired_not_deleted", sa.Integer(), nullable=False),
        sa.Column("pending_over_24h", sa.Integer(), nullable=False),
        sa.Column("exhausted_retries", sa.Integer(), nullable=False),
        sa.Column("deletion_failed", sa.Integer(), nullable=False),
        sa.Column("physically_deleted", sa.Integer(), nullable=False),
        sa.Column("notification_sent", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "expired_not_deleted >= 0 AND pending_over_24h >= 0 "
            "AND exhausted_retries >= 0 AND deletion_failed >= 0 "
            "AND physically_deleted >= 0",
            name="ck_ll_retention_run_counts",
        ),
    )
    op.create_index(
        "ix_ll_retention_runs_checked_at",
        "little_legend_retention_runs", ["checked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_retention_runs_checked_at",
        table_name="little_legend_retention_runs",
    )
    op.drop_table("little_legend_retention_runs")
