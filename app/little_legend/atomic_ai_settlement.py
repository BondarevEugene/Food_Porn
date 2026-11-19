"""A completed AI request settles both the ledger and budget atomically."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import (
    BookBudget,
    BudgetReservationStatus,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import (
    EffectStatus,
    production_effects,
)


async def confirm_ai_charge(
    *, owner_id: int, story_id: int, effect_key: str,
    actual_micro_usd: int, provider_reference: str,
) -> BookBudget:
    """Settle a single dispatched effect without double charging."""
    if not isinstance(actual_micro_usd, int) or isinstance(
        actual_micro_usd, bool,
    ) or actual_micro_usd < 0:
        raise ValueError("Invalid actual AI charge")
    if not provider_reference or len(provider_reference) > 160:
        raise ValueError("Provider acknowledgement required")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        budget_row = (await session.execute(select(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if budget_row is None:
            raise PermissionError("Book budget not found")
        effect = (await session.execute(select(production_effects).where(
            production_effects.c.effect_key == effect_key,
            production_effects.c.story_id == story_id,
            production_effects.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if effect is None or effect["status"] != EffectStatus.DISPATCHED.value:
            raise PermissionError("AI effect is not awaiting confirmation")
        reservation = (await session.execute(select(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
            budget_reservations.c.story_id == story_id,
            budget_reservations.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if reservation is None or reservation["status"] != "held":
            raise PermissionError("AI budget reservation missing")
        reserved = reservation["reserved_micro_usd"]
        if actual_micro_usd > reserved:
            raise PermissionError("AI charge exceeds reserved ceiling")
        budget = BookBudget.model_validate(dict(budget_row))
        changed = budget.model_copy(update={
            "held_micro_usd": budget.held_micro_usd - reserved,
            "spent_micro_usd": budget.spent_micro_usd + actual_micro_usd,
        })
        await session.execute(update(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
        ).values(
            status=BudgetReservationStatus.SETTLED.value,
            actual_micro_usd=actual_micro_usd,
            updated_at=now,
        ))
        await session.execute(update(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).values(
            held_micro_usd=changed.held_micro_usd,
            spent_micro_usd=changed.spent_micro_usd,
            updated_at=now,
        ))
        await session.execute(update(production_effects).where(
            production_effects.c.effect_key == effect_key,
        ).values(
            status=EffectStatus.CONFIRMED.value,
            provider_reference=provider_reference,
            updated_at=now,
        ))
        await session.commit()
        return changed
