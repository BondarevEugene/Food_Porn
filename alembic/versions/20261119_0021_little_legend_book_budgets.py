"""Per-book micro-USD budgets and effect reservations.

Revision ID: 20261119_0021
Revises: 20261119_0020
"""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0021"
down_revision = "20261119_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_book_budgets",
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("limit_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("held_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("spent_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "limit_micro_usd > 0 AND held_micro_usd >= 0 "
            "AND spent_micro_usd >= 0 AND "
            "held_micro_usd + spent_micro_usd <= limit_micro_usd",
            name="ck_ll_budget_within_limit",
        ),
    )
    op.create_index(
        "ix_little_legend_book_budgets_owner_id",
        "little_legend_book_budgets", ["owner_id"],
    )
    op.create_table(
        "little_legend_budget_reservations",
        sa.Column("effect_key", sa.String(120), primary_key=True),
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("reserved_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("actual_micro_usd", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reserved_micro_usd > 0",
            name="ck_ll_budget_reservation_positive",
        ),
        sa.CheckConstraint(
            "status IN ('held', 'settled', 'released')",
            name="ck_ll_budget_reservation_status",
        ),
        sa.CheckConstraint(
            "actual_micro_usd IS NULL OR "
            "(actual_micro_usd >= 0 AND "
            "actual_micro_usd <= reserved_micro_usd)",
            name="ck_ll_budget_actual_ceiling",
        ),
    )
    op.create_index(
        "ix_little_legend_budget_reservations_story_id",
        "little_legend_budget_reservations", ["story_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_little_legend_budget_reservations_story_id",
        table_name="little_legend_budget_reservations",
    )
    op.drop_table("little_legend_budget_reservations")
    op.drop_index(
        "ix_little_legend_book_budgets_owner_id",
        table_name="little_legend_book_budgets",
    )
    op.drop_table("little_legend_book_budgets")
