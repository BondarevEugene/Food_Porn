"""Bounded per-book AI budget provisioned at story creation.

This is a spending ceiling, not a payment, provider charge or customer price.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.book_budget_store import book_budgets

DEFAULT_BOOK_BUDGET_MICRO_USD = 5_000_000
MAX_BOOK_BUDGET_MICRO_USD = 20_000_000


def configured_book_budget_micro_usd() -> int:
    raw = os.getenv(
        "LITTLE_LEGEND_BOOK_AI_BUDGET_MICRO_USD",
        str(DEFAULT_BOOK_BUDGET_MICRO_USD),
    )
    try:
        amount = int(raw)
    except ValueError as exc:
        raise ValueError("Invalid Little Legend book AI budget") from exc
    if not 1 <= amount <= MAX_BOOK_BUDGET_MICRO_USD:
        raise ValueError("Little Legend book AI budget outside safe bounds")
    return amount


async def provision_story_budget(
    session: AsyncSession, *, story_id: int, owner_id: int,
    limit_micro_usd: int,
) -> None:
    """Insert only in caller's transaction, after owner-scoped story creation."""
    if (
        not isinstance(story_id, int) or isinstance(story_id, bool)
        or not isinstance(owner_id, int) or isinstance(owner_id, bool)
        or story_id <= 0 or owner_id <= 0
        or not isinstance(limit_micro_usd, int)
        or isinstance(limit_micro_usd, bool)
        or not 1 <= limit_micro_usd <= MAX_BOOK_BUDGET_MICRO_USD
    ):
        raise ValueError("Invalid story budget identity or ceiling")
    now = datetime.now(UTC)
    await session.execute(pg_insert(book_budgets).values(
        story_id=story_id, owner_id=owner_id,
        limit_micro_usd=limit_micro_usd,
        held_micro_usd=0, spent_micro_usd=0, updated_at=now,
    ))
