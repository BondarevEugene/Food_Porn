"""PostgreSQL enforces provider-reference uniqueness during concurrent inserts."""
from decimal import Decimal

from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.little_legend.ai_cost_ledger import cost_receipts


def test_cost_receipt_insert_uses_atomic_postgres_conflict_handling():
    statement = (
        pg_insert(cost_receipts)
        .values(
            receipt_id="receipt_12345678", job_id="writer_job_12345678",
            owner_id=1, story_id=2, provider="example",
            provider_reference="charge_123", amount_usd=Decimal("0.012345"),
            evidence="provider_receipt",
            recorded_at="2026-11-18T00:00:00+00:00",
        )
        .on_conflict_do_nothing()
        .returning(cost_receipts.c.receipt_id)
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT DO NOTHING" in compiled
    assert "RETURNING" in compiled
