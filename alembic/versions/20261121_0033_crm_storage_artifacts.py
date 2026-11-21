"""Create protected CRM storage artifact registry.

Revision ID: 20261121_0033
Revises: 20261121_0032
"""
import sqlalchemy as sa

from alembic import op

revision = "20261121_0033"
down_revision = "20261121_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_storage_artifacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bot_id", sa.String(40), nullable=False),
        sa.Column("connection", sa.String(60), nullable=False),
        sa.Column("bucket", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("order_type", sa.String(40), nullable=False),
        sa.Column("order_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("etag", sa.String(255)),
        sa.Column("state", sa.String(24), nullable=False, server_default="protected"),
        sa.Column("retention_hold", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bytes >= 0", name="ck_crm_storage_artifact_size"),
        sa.CheckConstraint(
            "state IN ('protected', 'orphan_candidate', 'quarantined', 'deleted')",
            name="ck_crm_storage_artifact_state",
        ),
        sa.UniqueConstraint(
            "connection", "bucket", "object_key",
            name="uq_crm_storage_artifact_object",
        ),
    )
    op.create_index(
        "ix_crm_storage_artifact_order", "crm_storage_artifacts",
        ["bot_id", "order_type", "order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_crm_storage_artifact_order", table_name="crm_storage_artifacts")
    op.drop_table("crm_storage_artifacts")
