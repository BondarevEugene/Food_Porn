"""Versioned Little Legend parental consent audit records.

Revision ID: 20261118_0018
Revises: 20261118_0017
"""
import sqlalchemy as sa

from alembic import op

revision = "20261118_0018"
down_revision = "20261118_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "little_legend_consent_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('terms_accepted', 'photo_withdrawn')",
            name="ck_ll_consent_event_type",
        ),
    )
    op.create_index(
        "ix_ll_consent_owner_story_created",
        "little_legend_consent_events",
        ["owner_id", "story_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_consent_owner_story_created",
        table_name="little_legend_consent_events",
    )
    op.drop_table("little_legend_consent_events")
