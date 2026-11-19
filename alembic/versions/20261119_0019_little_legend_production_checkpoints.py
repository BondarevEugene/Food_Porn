"""Persistent checkpoints for Little Legend production.

Revision ID: 20261119_0019
Revises: 20261118_0018
"""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0019"
down_revision = "20261118_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_production_checkpoints",
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("release_fingerprint", sa.String(64), nullable=True),
        sa.Column("pdf_sha256", sa.String(64), nullable=True),
        sa.Column("delivery_message_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 0", name="ck_ll_checkpoint_version"),
        sa.CheckConstraint(
            "phase IN ('draft', 'manuscript_approved', 'art_approved', "
            "'pdf_sealed', 'delivery_pending', 'delivered')",
            name="ck_ll_checkpoint_phase",
        ),
    )
    op.create_index(
        "ix_little_legend_production_checkpoints_owner_id",
        "little_legend_production_checkpoints", ["owner_id"],
    )
    op.create_index(
        "ix_little_legend_production_checkpoints_phase",
        "little_legend_production_checkpoints", ["phase"],
    )
    op.create_index(
        "ix_ll_production_owner_phase_updated",
        "little_legend_production_checkpoints",
        ["owner_id", "phase", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_production_owner_phase_updated",
        table_name="little_legend_production_checkpoints",
    )
    op.drop_index(
        "ix_little_legend_production_checkpoints_phase",
        table_name="little_legend_production_checkpoints",
    )
    op.drop_index(
        "ix_little_legend_production_checkpoints_owner_id",
        table_name="little_legend_production_checkpoints",
    )
    op.drop_table("little_legend_production_checkpoints")
