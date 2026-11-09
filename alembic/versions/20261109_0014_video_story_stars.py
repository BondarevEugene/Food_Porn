"""Add independent Stars amount to video story orders.

Revision ID: 20261109_0014
Revises: 20261109_0013
"""

import sqlalchemy as sa
from alembic import op

revision = "20261109_0014"
down_revision = "20261109_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_story_orders", sa.Column("stars_amount", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_story_orders", "stars_amount")
