"""Audit ledger for paid Little Legend effects and delivery.

Revision ID: 20261119_0020
Revises: 20261119_0019
"""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0020"
down_revision = "20261119_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_production_effects",
        sa.Column("effect_key", sa.String(120), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_reference", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('writer_ai', 'illustration_ai', 'telegram_pdf')",
            name="ck_ll_effect_kind",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'dispatched', 'confirmed', 'uncertain')",
            name="ck_ll_effect_status",
        ),
    )
    for column in ("owner_id", "story_id", "status"):
        op.create_index(
            f"ix_little_legend_production_effects_{column}",
            "little_legend_production_effects", [column],
        )
    op.create_index(
        "ix_ll_effect_owner_status_created",
        "little_legend_production_effects",
        ["owner_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_effect_owner_status_created",
        table_name="little_legend_production_effects",
    )
    for column in ("status", "story_id", "owner_id"):
        op.drop_index(
            f"ix_little_legend_production_effects_{column}",
            table_name="little_legend_production_effects",
        )
    op.drop_table("little_legend_production_effects")
