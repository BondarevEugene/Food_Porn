"""Little Legend story and private media registry in Neon PostgreSQL.

Revision ID: 20261118_0016
Revises: 20261113_0015
"""
import sqlalchemy as sa

from alembic import op

revision = "20261118_0016"
down_revision = "20261113_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older deployments created stories at app startup. Preserve existing rows.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("little_legend_stories"):
        op.create_table(
            "little_legend_stories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_id", sa.BigInteger(), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("hero", sa.String(length=100), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_little_legend_stories_owner_id",
            "little_legend_stories",
            ["owner_id"],
        )
    op.create_table(
        "little_legend_vault_assets",
        sa.Column("asset_id", sa.String(length=48), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "story_id", sa.Integer(),
            sa.ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=120), nullable=False, unique=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deletion_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.CheckConstraint("deletion_attempts >= 0", name="ck_ll_vault_attempts"),
    )
    op.create_index(
        "ix_ll_vault_owner_story", "little_legend_vault_assets",
        ["owner_id", "story_id"],
    )
    op.create_index(
        "ix_ll_vault_expiry", "little_legend_vault_assets",
        ["state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ll_vault_expiry", table_name="little_legend_vault_assets")
    op.drop_index("ix_ll_vault_owner_story", table_name="little_legend_vault_assets")
    op.drop_table("little_legend_vault_assets")
    # Never drop little_legend_stories: it may predate this migration and
    # contains customer-authored content.
