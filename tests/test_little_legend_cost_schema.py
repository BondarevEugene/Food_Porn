"""Cost ledger is created by the existing Little Legend schema initializer."""
from app.little_legend.ai_cost_ledger import cost_receipts, ledger_metadata
from app.little_legend.writer_queue_store import writer_jobs


def test_cost_receipts_schema_has_provider_scoped_unique_reference():
    assert cost_receipts.name == "little_legend_ai_cost_receipts"
    assert cost_receipts.metadata is ledger_metadata
    assert not cost_receipts.c.owner_id.nullable
    assert not cost_receipts.c.amount_usd.nullable
    assert cost_receipts.c.job_id.foreign_keys
    fk = next(iter(cost_receipts.c.job_id.foreign_keys))
    assert fk.column is writer_jobs.c.job_id
    assert any(
        set(constraint.columns.keys()) == {"provider", "provider_reference"}
        for constraint in cost_receipts.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
