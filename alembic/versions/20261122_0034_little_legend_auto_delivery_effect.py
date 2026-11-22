"""Allow durable Little Legend automatic PDF delivery requests.

Revision ID: 20261122_0034
Revises: 20261121_0033
"""
import sqlalchemy as sa

from alembic import op

revision = "20261122_0034"
down_revision = "20261121_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_ll_effect_kind",
        "little_legend_production_effects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ll_effect_kind",
        "little_legend_production_effects",
        "kind IN ('writer_ai', 'illustration_ai', 'telegram_pdf', "
        "'telegram_auto_request')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        sa.text(
            "SELECT 1 FROM little_legend_production_effects "
            "WHERE kind = 'telegram_auto_request' LIMIT 1"
        )
    ).first()
    if existing is not None:
        raise RuntimeError(
            "Cannot downgrade while automatic delivery requests exist"
        )
    op.drop_constraint(
        "ck_ll_effect_kind",
        "little_legend_production_effects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ll_effect_kind",
        "little_legend_production_effects",
        "kind IN ('writer_ai', 'illustration_ai', 'telegram_pdf')",
    )
