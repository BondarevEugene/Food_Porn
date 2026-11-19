"""Immutable owner-scoped book price quotes; no payments are accepted here."""
import sqlalchemy as sa
from alembic import op

revision = "20261119_0023"
down_revision = "20261119_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_order_quotes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("story_id", sa.Integer(),
                  sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("edition", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("story_id", "edition", name="uq_ll_quote_story_edition"),
        sa.CheckConstraint("edition IN ('digital', 'print')", name="ck_ll_quote_edition"),
        sa.CheckConstraint("currency = 'UAH'", name="ck_ll_quote_currency"),
        sa.CheckConstraint("price_minor > 0", name="ck_ll_quote_positive_price"),
        sa.CheckConstraint("status = 'quoted'", name="ck_ll_quote_unpaid"),
    )
    op.create_index("ix_ll_quotes_owner_id", "little_legend_order_quotes", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_ll_quotes_owner_id", table_name="little_legend_order_quotes")
    op.drop_table("little_legend_order_quotes")
