"""Persist dedicated parent consent for transfer of child photos to AI.

Revision ID: 20261121_0032
Revises: 20261121_0031
"""
import sqlalchemy as sa

from alembic import op

revision = "20261121_0032"
down_revision = "20261121_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_premium_photo_consents",
        sa.Column("story_id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(200), nullable=False),
        sa.Column("notice_snapshot", sa.String(4000), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("owner_id > 0", name="ck_ll_premium_photo_owner"),
    )
    op.create_index(
        "ix_ll_premium_photo_owner_story",
        "little_legend_premium_photo_consents", ["owner_id", "story_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_premium_photo_owner_story",
        table_name="little_legend_premium_photo_consents",
    )
    op.drop_table("little_legend_premium_photo_consents")
