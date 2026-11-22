"""Ensure the automatic delivery migration extends the existing effect ledger."""
from pathlib import Path


def test_auto_delivery_migration_is_forward_only_and_preserves_ledger():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20261122_0034_little_legend_auto_delivery_effect.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'down_revision = "20261121_0033"' in source
    assert "'telegram_auto_request'" in source
    assert 'op.create_check_constraint(' in source
    assert 'op.drop_table(' not in source
    assert 'op.create_table(' not in source
    assert "Cannot downgrade while automatic delivery requests exist" in source


def test_auto_delivery_uses_migrated_effect_kind():
    from app.little_legend.production_effect_ledger import EffectKind

    assert EffectKind.TELEGRAM_AUTO_REQUEST.value == "telegram_auto_request"
