"""Verified Little Legend payment receipts, separate from unpaid quotes."""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0024"
down_revision = "20261119_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_payment_receipts",
        sa.Column("quote_id", sa.BigInteger(),
                  sa.ForeignKey("little_legend_order_quotes.id", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(120), nullable=False, unique=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_ll_receipt_positive"),
        sa.CheckConstraint("currency = 'UAH'", name="ck_ll_receipt_currency"),
        sa.CheckConstraint("provider = 'wayforpay'", name="ck_ll_receipt_provider"),
    )
    op.create_index(
        "ix_ll_receipt_owner_id", "little_legend_payment_receipts", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_receipt_owner_id", table_name="little_legend_payment_receipts"
    )
    op.drop_table("little_legend_payment_receipts")
