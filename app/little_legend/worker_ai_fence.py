"""Authorize an AI worker dispatch inside the caller's existing transaction.

The caller must already hold its job row lock and validate its lease, story
revision and consent. This function locks the book budget, writes the effect
fence and reserves money without committing; caller commits all changes once.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.book_budget_store import (
    BookBudget,
    BudgetReservationStatus,
    available_micro_usd,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
    production_effects,
    request_fingerprint,
)
from app.little_legend.writer_queue import WriterJob


async def fence_worker_ai_effect(
    session: AsyncSession, *, job: WriterJob, kind: EffectKind,
) -> None:
    """Raise on duplicate or over-budget requests; do not commit or call AI."""
    if kind not in {EffectKind.WRITER_AI, EffectKind.ILLUSTRATION_AI}:
        raise ValueError("AI worker effect kind required")
    if job.provider_dispatched_at is not None:
        raise PermissionError("Job was already dispatched")
    if job.estimated_cost_usd <= 0:
        raise PermissionError("Job has no positive AI cost estimate")
    # Round up so the reserved ceiling is never below the estimate.
    amount = int(
        (Decimal(str(job.estimated_cost_usd)) * 1_000_000).to_integral_value(
            rounding=ROUND_CEILING,
        )
    )
    effect_key = "llai:" + hashlib.sha256(\n        f"{kind.value}:{job.job_id}".encode("utf-8")\n    ).hexdigest()
    fingerprint = request_fingerprint({
        "kind": kind.value, "job_id": job.job_id,
        "story_id": job.story_id, "owner_id": job.owner_id,
        "scene_id": job.scene_id, "revision": job.expected_revision,
    })
    now = datetime.now(UTC)
    budget_row = (await session.execute(select(book_budgets).where(
        book_budgets.c.owner_id == job.owner_id,
        book_budgets.c.story_id == job.story_id,
    ).with_for_update())).mappings().one_or_none()
    if budget_row is None:
        raise PermissionError("Book budget must be configured before AI dispatch")
    budget = BookBudget.model_validate(dict(budget_row))
    if available_micro_usd(budget) < amount:
        raise PermissionError("Book AI budget exceeded")
    candidate = ProductionEffect(
        effect_key=effect_key, owner_id=job.owner_id,
        story_id=job.story_id, kind=kind,
        request_sha256=fingerprint, created_at=now, updated_at=now,
    )
    inserted = (await session.execute(
        pg_insert(production_effects).values(
            **candidate.model_dump(mode="python"),
        ).on_conflict_do_nothing(index_elements=["effect_key"])
        .returning(production_effects.c.effect_key)
    )).scalar_one_or_none()
    if inserted is None:
        raise PermissionError("AI operation already reserved or dispatched")
    await session.execute(pg_insert(budget_reservations).values(
        effect_key=effect_key, owner_id=job.owner_id,
        story_id=job.story_id, reserved_micro_usd=amount,
        status=BudgetReservationStatus.HELD.value, updated_at=now,
    ))
    await session.execute(update(book_budgets).where(
        book_budgets.c.story_id == job.story_id,
        book_budgets.c.owner_id == job.owner_id,
    ).values(
        held_micro_usd=budget.held_micro_usd + amount,
        updated_at=now,
    ))
    await session.execute(update(production_effects).where(
        production_effects.c.effect_key == effect_key,
        production_effects.c.status == EffectStatus.RESERVED.value,
    ).values(status=EffectStatus.DISPATCHED.value, updated_at=now))
