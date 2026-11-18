"""Little Legend deletion retry scheduling and operational indexes.

Revision ID: 20261118_0017
Revises: 20261118_0016
"""
import sqlalchemy as sa

from alembic import op

revision = "20261118_0017"
down_revision = "20261118_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "little_legend_vault_assets",
        sa.Column("last_deletion_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "little_legend_vault_assets",
        sa.Column("next_deletion_attempt_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_ll_vault_retry_due",
        "little_legend_vault_assets",
        ["state", "next_deletion_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ll_vault_retry_due", table_name="little_legend_vault_assets"
    )
    op.drop_column("little_legend_vault_assets", "next_deletion_attempt_at")
    op.drop_column("little_legend_vault_assets", "last_deletion_attempt_at")
