"""Persist private Little Legend photo metadata without image bytes.

Revision ID: 20261121_0031
Revises: 20261120_0030
"""
import sqlalchemy as sa

from alembic import op

revision = "20261121_0031"
down_revision = "20261120_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_photo_assets",
        sa.Column("asset_id", sa.String(48), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.CheckConstraint("owner_id > 0", name="ck_ll_photo_owner_positive"),
        sa.CheckConstraint("story_id > 0", name="ck_ll_photo_story_positive"),
        sa.CheckConstraint("expires_at > created_at", name="ck_ll_photo_expiry"),
    )
    op.create_index(
        "ix_ll_photo_owner_story",
        "little_legend_photo_assets", ["owner_id", "story_id"],
    )
    op.create_index(
        "ix_ll_photo_expiry_state",
        "little_legend_photo_assets", ["state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ll_photo_expiry_state", table_name="little_legend_photo_assets")
    op.drop_index("ix_ll_photo_owner_story", table_name="little_legend_photo_assets")
    op.drop_table("little_legend_photo_assets")
