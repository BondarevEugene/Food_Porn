"""Read-only integrity audit for per-book AI accounting.

No personal story text, image content or provider credentials are returned.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import (
    BudgetReservationStatus,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import EffectStatus, production_effects


class BudgetAuditItem(BaseModel):
    story_id: int = Field(gt=0)
    owner_id: int = Field(gt=0)
    held_micro_usd: int
    spent_micro_usd: int
    recorded_held_micro_usd: int
    recorded_spent_micro_usd: int
    unresolved_effects: int
    consistent: bool


def classify_budget_audit(
    *, story_id: int, owner_id: int,
    held_micro_usd: int, spent_micro_usd: int,
    recorded_held_micro_usd: int, recorded_spent_micro_usd: int,
    unresolved_effects: int,
) -> BudgetAuditItem:
    return BudgetAuditItem(
        story_id=story_id, owner_id=owner_id,
        held_micro_usd=held_micro_usd,
        spent_micro_usd=spent_micro_usd,
        recorded_held_micro_usd=recorded_held_micro_usd,
        recorded_spent_micro_usd=recorded_spent_micro_usd,
        unresolved_effects=unresolved_effects,
        consistent=(
            held_micro_usd >= 0 and spent_micro_usd >= 0
            and held_micro_usd == recorded_held_micro_usd
            and spent_micro_usd == recorded_spent_micro_usd
        ),
    )


async def audit_book_budgets(
    *, owner_id: int, limit: int = 100,
) -> list[BudgetAuditItem]:
    if owner_id <= 0 or not 1 <= limit <= 500:
        raise ValueError("Invalid owner or audit limit")
    async with async_session_maker() as session:
        budgets = (await session.execute(select(book_budgets).where(
            book_budgets.c.owner_id == owner_id,
        ).order_by(book_budgets.c.story_id).limit(limit))).mappings().all()
        result = []
        for budget in budgets:
            amounts = (await session.execute(select(
                func.coalesce(func.sum(
                    budget_reservations.c.reserved_micro_usd,
                ).filter(
                    budget_reservations.c.status
                    == BudgetReservationStatus.HELD.value,
                ), 0),
                func.coalesce(func.sum(
                    budget_reservations.c.actual_micro_usd,
                ).filter(
                    budget_reservations.c.status
                    == BudgetReservationStatus.SETTLED.value,
                ), 0),
            ).where(
                budget_reservations.c.story_id == budget["story_id"],
                budget_reservations.c.owner_id == owner_id,
            ))).one()
            unresolved = (await session.execute(select(
                func.count(production_effects.c.effect_key),
            ).where(
                production_effects.c.story_id == budget["story_id"],
                production_effects.c.owner_id == owner_id,
                production_effects.c.status.in_([
                    EffectStatus.DISPATCHED.value,
                    EffectStatus.UNCERTAIN.value,
                ]),
            ))).scalar_one()
            result.append(classify_budget_audit(
                story_id=budget["story_id"], owner_id=owner_id,
                held_micro_usd=budget["held_micro_usd"],
                spent_micro_usd=budget["spent_micro_usd"],
                recorded_held_micro_usd=int(amounts[0]),
                recorded_spent_micro_usd=int(amounts[1]),
                unresolved_effects=unresolved,
            ))
    return result
