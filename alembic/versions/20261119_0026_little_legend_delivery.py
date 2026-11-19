"""Durable book artifact and delivery claim metadata."""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0026"
down_revision = "20261119_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("asset_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("delivery_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "little_legend_fulfillment_jobs",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("little_legend_fulfillment_jobs", "delivered_at")
    op.drop_column("little_legend_fulfillment_jobs", "delivery_started_at")
    op.drop_column("little_legend_fulfillment_jobs", "asset_key")
