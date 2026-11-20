"""Add fenced production leases to Little Legend fulfillment.

Revision ID: 20261120_0029
Revises: 20261120_0028
"""
import sqlalchemy as sa

from alembic import op

revision = "20261120_0029"
down_revision = "20261120_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("lease_token", sa.String(36), nullable=True),
    )
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("lease_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_ll_fulfillment_lease_attempts",
        "little_legend_fulfillment_jobs",
        "lease_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_ll_fulfillment_lease_pair",
        "little_legend_fulfillment_jobs",
        "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
        "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ll_fulfillment_lease_pair",
        "little_legend_fulfillment_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_ll_fulfillment_lease_attempts",
        "little_legend_fulfillment_jobs",
        type_="check",
    )
    op.drop_column("little_legend_fulfillment_jobs", "lease_attempts")
    op.drop_column("little_legend_fulfillment_jobs", "lease_expires_at")
    op.drop_column("little_legend_fulfillment_jobs", "lease_token")
