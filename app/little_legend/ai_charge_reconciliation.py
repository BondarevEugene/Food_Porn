"""Owner-scoped reconciliation of ambiguous AI provider charges.

Unknown outcomes retain their budget hold. Only a trusted, verified provider
receipt can confirm the charge; this module never retries a provider request.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.database.session import async_session_maker
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


class PendingAICharge(BaseModel):
    effect_key: str
    story_id: int = Field(gt=0)
    kind: EffectKind
    status: EffectStatus
    reserved_micro_usd: int = Field(gt=0)
    updated_at: datetime


async def list_pending_ai_charges(
    *, owner_id: int, story_id: int, limit: int = 50,
) -> list[PendingAICharge]:
    """Show metadata only, excluding child prompts and provider credentials."""
    if not 1 <= limit <= 100:
        raise ValueError("Invalid page size")
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(
                production_effects.c.effect_key,
                production_effects.c.story_id,
                production_effects.c.kind,
                production_effects.c.status,
                budget_reservations.c.reserved_micro_usd,
                production_effects.c.updated_at,
            ).join(
                budget_reservations,
                budget_reservations.c.effect_key
                == production_effects.c.effect_key,
            ).where(
                production_effects.c.owner_id == owner_id,
                production_effects.c.story_id == story_id,
                production_effects.c.status.in_([
                    EffectStatus.DISPATCHED.value,
                    EffectStatus.UNCERTAIN.value,
                ]),
                budget_reservations.c.owner_id == owner_id,
                budget_reservations.c.story_id == story_id,
                budget_reservations.c.status
                == BudgetReservationStatus.HELD.value,
            ).order_by(
                production_effects.c.updated_at,
                production_effects.c.effect_key,
            ).limit(limit)
        )).mappings().all()
    return [PendingAICharge.model_validate(dict(row)) for row in rows]


async def mark_ai_charge_uncertain(
    *, owner_id: int, story_id: int, effect_key: str,
) -> None:
    """Record ambiguous provider result without releasing reserved funds."""
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        # Lock budget first, matching dispatch/settlement lock ordering.
        budget = (await session.execute(select(book_budgets.c.story_id).where(
            book_budgets.c.owner_id == owner_id,
            book_budgets.c.story_id == story_id,
        ).with_for_update())).scalar_one_or_none()
        if budget is None:
            raise PermissionError("Book budget not found")
        effect = (await session.execute(select(production_effects).where(
            production_effects.c.effect_key == effect_key,
            production_effects.c.owner_id == owner_id,
            production_effects.c.story_id == story_id,
        ).with_for_update())).mappings().one_or_none()
        if effect is None or effect["status"] not in {
            EffectStatus.DISPATCHED.value,
            EffectStatus.UNCERTAIN.value,
        }:
            raise PermissionError("AI operation is not awaiting reconciliation")
        if effect["kind"] not in {
            EffectKind.WRITER_AI.value,
            EffectKind.ILLUSTRATION_AI.value,
        }:
            raise PermissionError("Not an AI charge")
        reservation = (await session.execute(
            select(budget_reservations.c.effect_key).where(
                budget_reservations.c.effect_key == effect_key,
                budget_reservations.c.owner_id == owner_id,
                budget_reservations.c.story_id == story_id,
                budget_reservations.c.status
                == BudgetReservationStatus.HELD.value,
            ).with_for_update()
        )).scalar_one_or_none()
        if reservation is None:
            raise PermissionError("Held AI reservation not found")
        if effect["status"] == EffectStatus.DISPATCHED.value:
            await session.execute(update(production_effects).where(
                production_effects.c.effect_key == effect_key,
            ).values(
                status=EffectStatus.UNCERTAIN.value,
                updated_at=now,
            ))
        await session.commit()


async def reconcile_verified_ai_charge(
    *, owner_id: int, story_id: int, effect_key: str,
    actual_micro_usd: int, provider_reference: str,
    verified: bool = False,
) -> BookBudget:
    """Manually confirm a provider-verified receipt; no automatic retry."""
    if not verified:
        raise PermissionError("Provider receipt must be independently verified")
    if (
        not isinstance(actual_micro_usd, int)
        or isinstance(actual_micro_usd, bool)
        or actual_micro_usd < 0
    ):
        raise ValueError("Invalid actual charge")
    if not provider_reference or len(provider_reference) > 160:
        raise ValueError("Invalid provider receipt reference")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        row = (await session.execute(select(book_budgets).where(
            book_budgets.c.owner_id == owner_id,
            book_budgets.c.story_id == story_id,
        ).with_for_update())).mappings().one_or_none()
        if row is None:
            raise PermissionError("Book budget not found")
        effect = (await session.execute(select(production_effects).where(
            production_effects.c.effect_key == effect_key,
            production_effects.c.owner_id == owner_id,
            production_effects.c.story_id == story_id,
        ).with_for_update())).mappings().one_or_none()
        if effect is None or effect["status"] not in {
            EffectStatus.DISPATCHED.value,
            EffectStatus.UNCERTAIN.value,
        }:
            raise PermissionError("AI effect is not awaiting reconciliation")
        if effect["kind"] not in {
            EffectKind.WRITER_AI.value,
            EffectKind.ILLUSTRATION_AI.value,
        }:
            raise PermissionError("Not an AI charge")
        hold = (await session.execute(select(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
            budget_reservations.c.owner_id == owner_id,
            budget_reservations.c.story_id == story_id,
        ).with_for_update())).mappings().one_or_none()
        if hold is None or hold["status"] != BudgetReservationStatus.HELD.value:
            raise PermissionError("No unsettled AI reservation")
        reserved = hold["reserved_micro_usd"]
        if actual_micro_usd > reserved:
            raise PermissionError("Provider charge exceeds reserved ceiling")
        budget = BookBudget.model_validate(dict(row))
        updated = budget.model_copy(update={
            "held_micro_usd": budget.held_micro_usd - reserved,
            "spent_micro_usd": budget.spent_micro_usd + actual_micro_usd,
        })
        await session.execute(update(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).values(
            held_micro_usd=updated.held_micro_usd,
            spent_micro_usd=updated.spent_micro_usd,
            updated_at=now,
        ))
        await session.execute(update(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
        ).values(
            status=BudgetReservationStatus.SETTLED.value,
            actual_micro_usd=actual_micro_usd,
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
        return updated
