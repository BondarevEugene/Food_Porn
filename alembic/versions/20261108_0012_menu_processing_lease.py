"""Add database-backed leases for distributed menu generation.

Revision ID: 20261108_0012
Revises: 20261108_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261108_0012"
down_revision: str | None = "20261108_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("menus", sa.Column("processing_token", sa.String(length=64), nullable=True))
    op.add_column("menus", sa.Column("processing_lease_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("menus", "processing_lease_until")
    op.drop_column("menus", "processing_token")
