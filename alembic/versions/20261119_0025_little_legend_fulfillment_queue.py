"""Durable paid-book fulfillment queue."""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0025"
down_revision = "20261119_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_fulfillment_jobs",
        sa.Column(
            "quote_id", sa.BigInteger(),
            sa.ForeignKey("little_legend_order_quotes.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'blocked', 'processing', 'ready', 'failed')",
            name="ck_ll_fulfillment_status",
        ),
    )
    op.create_index(
        "ix_ll_fulfillment_owner_id", "little_legend_fulfillment_jobs", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_fulfillment_owner_id", table_name="little_legend_fulfillment_jobs"
    )
    op.drop_table("little_legend_fulfillment_jobs")
