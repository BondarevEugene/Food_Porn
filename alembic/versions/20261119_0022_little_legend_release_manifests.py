"""Persist immutable Little Legend PDF release metadata.

Revision ID: 20261119_0022
Revises: 20261119_0021
"""
import sqlalchemy as sa

from alembic import op

revision = "20261119_0022"
down_revision = "20261119_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_release_manifests",
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_fingerprint", sa.String(64), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("scene_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scene_count BETWEEN 1 AND 40", name="ck_ll_release_scene_count",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'sent', 'uncertain')",
            name="ck_ll_release_status",
        ),
        sa.CheckConstraint(
            "(status = 'sent' AND telegram_message_id > 0) OR "
            "(status <> 'sent' AND telegram_message_id IS NULL)",
            name="ck_ll_release_message_state",
        ),
    )
    op.create_index(
        "ix_little_legend_release_manifests_owner_id",
        "little_legend_release_manifests", ["owner_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_little_legend_release_manifests_owner_id",
        table_name="little_legend_release_manifests",
    )
    op.drop_table("little_legend_release_manifests")
