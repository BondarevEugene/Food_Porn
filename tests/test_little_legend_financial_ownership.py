"""Ownership checks must precede all budget and effect inserts."""
from pathlib import Path

import pytest

from app.little_legend.book_budget_store import configure_book_budget


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_id", "story_id"),
    [(0, 1), (-1, 1), (1, 0), (1, -1)],
)
async def test_invalid_budget_identity_rejected_before_database(
    owner_id: int, story_id: int,
) -> None:
    with pytest.raises(ValueError, match="Positive owner"):
        await configure_book_budget(
            owner_id=owner_id, story_id=story_id, limit_micro_usd=1000,
        )


def test_budget_ownership_check_precedes_insert() -> None:
    source = Path("app/little_legend/book_budget_store.py").read_text(
        encoding="utf-8",
    )
    body = source.split("async def configure_book_budget(", 1)[1]
    body = body.split("async def reserve_ai_budget(", 1)[0]
    assert body.index("owned_story =") < body.index(
        "pg_insert(book_budgets)"
    )


def test_effect_ownership_check_precedes_insert() -> None:
    source = Path("app/little_legend/production_effect_ledger.py").read_text(
        encoding="utf-8",
    )
    body = source.split("async def reserve_effect(", 1)[1]
    body = body.split("async def transition_effect(", 1)[0]
    assert body.index("owned_story =") < body.index(
        "pg_insert(production_effects)"
    )
