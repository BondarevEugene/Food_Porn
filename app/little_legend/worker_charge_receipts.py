"""Settle a verified worker charge in the same transaction as job completion.

Only the trusted worker should supply provider receipts. Never derive a charge
from the estimated cost or automatically settle ambiguous provider outcomes.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.book_budget_store import (
    BookBudget,
    BudgetReservationStatus,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    production_effects,
)
from app.little_legend.writer_queue import WriterJob


def worker_effect_key(*, job_id: str, kind: EffectKind) -> str:
    if kind not in {EffectKind.WRITER_AI, EffectKind.ILLUSTRATION_AI}:
        raise ValueError("Paid worker effect kind required")
    return "llai:" + hashlib.sha256(f"{kind.value}:{job_id}".encode()).hexdigest()


def validate_provider_receipt(
    *, actual_micro_usd: int | None, provider_reference: str | None,
) -> bool:
    if actual_micro_usd is None and provider_reference is None:
        return False
    if (
        not isinstance(actual_micro_usd, int)
        or isinstance(actual_micro_usd, bool)
        or actual_micro_usd < 0
        or not isinstance(provider_reference, str)
        or not 1 <= len(provider_reference) <= 160
    ):
        raise ValueError("Complete, valid provider receipt required")
    return True


async def settle_worker_receipt(
    session: AsyncSession, *, job: WriterJob, kind: EffectKind,
    actual_micro_usd: int, provider_reference: str,
) -> None:
    """Caller holds job row lock; caller alone commits job and ledger changes."""
    validate_provider_receipt(
        actual_micro_usd=actual_micro_usd,
        provider_reference=provider_reference,
    )
    if job.provider_dispatched_at is None:
        raise PermissionError("Worker has no recorded provider dispatch")
    key = worker_effect_key(job_id=job.job_id, kind=kind)
    now = datetime.now(UTC)
    budget_row = (await session.execute(select(book_budgets).where(
        book_budgets.c.story_id == job.story_id,
        book_budgets.c.owner_id == job.owner_id,
    ).with_for_update())).mappings().one_or_none()
    if budget_row is None:
        raise PermissionError("Book budget missing")
    effect = (await session.execute(select(production_effects).where(
        production_effects.c.effect_key == key,
        production_effects.c.story_id == job.story_id,
        production_effects.c.owner_id == job.owner_id,
        production_effects.c.kind == kind.value,
    ).with_for_update())).mappings().one_or_none()
    if effect is None or effect["status"] != EffectStatus.DISPATCHED.value:
        raise PermissionError("AI effect is not awaiting confirmation")
    reservation = (await session.execute(select(budget_reservations).where(
        budget_reservations.c.effect_key == key,
        budget_reservations.c.story_id == job.story_id,
        budget_reservations.c.owner_id == job.owner_id,
    ).with_for_update())).mappings().one_or_none()
    if reservation is None or reservation["status"] != BudgetReservationStatus.HELD.value:
        raise PermissionError("AI reservation missing")
    reserved = reservation["reserved_micro_usd"]
    if actual_micro_usd > reserved:
        raise PermissionError("Provider charge exceeds reserved ceiling")
    budget = BookBudget.model_validate(dict(budget_row))
    await session.execute(update(budget_reservations).where(
        budget_reservations.c.effect_key == key,
    ).values(
        status=BudgetReservationStatus.SETTLED.value,
        actual_micro_usd=actual_micro_usd, updated_at=now,
    ))
    await session.execute(update(book_budgets).where(
        book_budgets.c.story_id == job.story_id,
        book_budgets.c.owner_id == job.owner_id,
    ).values(
        held_micro_usd=budget.held_micro_usd - reserved,
        spent_micro_usd=budget.spent_micro_usd + actual_micro_usd,
        updated_at=now,
    ))
    await session.execute(update(production_effects).where(
        production_effects.c.effect_key == key,
    ).values(
        status=EffectStatus.CONFIRMED.value,
        provider_reference=provider_reference,
        updated_at=now,
    ))
