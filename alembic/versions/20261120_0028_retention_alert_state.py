"""Durable retention alert delivery state.

Revision ID: 20261120_0028
Revises: 20261120_0027
"""
import sqlalchemy as sa

from alembic import op

revision = "20261120_0028"
down_revision = "20261120_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_retention_alert_state",
        sa.Column("scope", sa.String(32), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("little_legend_retention_alert_state")
