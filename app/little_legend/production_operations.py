"""Owner-scoped production operations: leases, AI budget, effect ledger.

Read-only recovery assessment. It does not call providers, retry AI, change
payments, or release held money. Ambiguous side effects fail closed.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.book_budget_store import book_budgets, budget_reservations
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.production_effect_ledger import production_effects
from app.little_legend.production_leases import LeaseDiagnosis, diagnose_lease


class RecoveryAction(StrEnum):
    WAIT = "wait"
    READY = "ready"
    MANUAL_REVIEW = "manual_review"
    QUEUED = "queued"
    BLOCKED = "blocked"


class ProductionOperationsView(BaseModel):
    quote_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    fulfillment_status: str
    lease_diagnosis: LeaseDiagnosis
    lease_attempts: int = Field(ge=0)
    recovery_action: RecoveryAction
    budget_limit_micro_usd: int | None = Field(default=None, ge=0)
    budget_held_micro_usd: int | None = Field(default=None, ge=0)
    budget_spent_micro_usd: int | None = Field(default=None, ge=0)
    unresolved_effects: int = Field(ge=0)
    held_reservations: int = Field(ge=0)
    automatic_retry_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


def recommend_recovery(
    *, diagnosis: LeaseDiagnosis, unresolved_effects: int,
    held_reservations: int, has_budget: bool,
) -> tuple[RecoveryAction, list[str]]:
    """Classify operational risk; never authorize an external retry."""
    if unresolved_effects < 0 or held_reservations < 0:
        raise ValueError("Invalid recovery counters")
    notes: list[str] = []
    if unresolved_effects or held_reservations:
        notes.append("Unreconciled provider effects or held AI funds; manual audit required")
        return RecoveryAction.MANUAL_REVIEW, notes
    if diagnosis in {LeaseDiagnosis.STALE_REVIEW, LeaseDiagnosis.FAILED_REVIEW}:
        notes.append("Production attempt may have incurred charges; manual audit required")
        return RecoveryAction.MANUAL_REVIEW, notes
    if diagnosis == LeaseDiagnosis.ACTIVE:
        return RecoveryAction.WAIT, ["Worker lease is active"]
    if diagnosis == LeaseDiagnosis.READY:
        return RecoveryAction.READY, ["Production completed; verify delivery separately"]
    if diagnosis == LeaseDiagnosis.BLOCKED:
        return RecoveryAction.BLOCKED, ["Production blocked; inspect release gates"]
    if not has_budget:
        return RecoveryAction.BLOCKED, ["AI budget has not been provisioned"]
    return RecoveryAction.QUEUED, ["Pending paid job; worker dispatch requires separate gates"]


async def inspect_production_operations(
    session: AsyncSession, *, quote_id: int, owner_id: int,
) -> ProductionOperationsView | None:
    """Single owner-scoped quote; aggregate counters, no child text or image."""
    if quote_id <= 0 or owner_id <= 0:
        raise ValueError("Invalid quote or owner")
    quote = (await session.execute(
        select(order_quotes.c.story_id).where(
            order_quotes.c.id == quote_id,
            order_quotes.c.owner_id == owner_id,
        )
    )).scalar_one_or_none()
    if quote is None:
        return None
    row = (await session.execute(select(
        fulfillment_jobs.c.status,
        fulfillment_jobs.c.lease_expires_at,
        fulfillment_jobs.c.lease_attempts,
    ).where(
        fulfillment_jobs.c.quote_id == quote_id,
        fulfillment_jobs.c.owner_id == owner_id,
    ))).one_or_none()
    if row is None:
        return None
    budget = (await session.execute(select(
        book_budgets.c.limit_micro_usd,
        book_budgets.c.held_micro_usd,
        book_budgets.c.spent_micro_usd,
    ).where(
        book_budgets.c.story_id == quote,
        book_budgets.c.owner_id == owner_id,
    ))).one_or_none()
    unresolved = (await session.execute(select(func.count()).select_from(
        production_effects,
    ).where(
        production_effects.c.story_id == quote,
        production_effects.c.owner_id == owner_id,
        production_effects.c.status.in_(("reserved", "dispatched", "uncertain")),
    ))).scalar_one()
    held = (await session.execute(select(func.count()).select_from(
        budget_reservations,
    ).where(
        budget_reservations.c.story_id == quote,
        budget_reservations.c.owner_id == owner_id,
        budget_reservations.c.status == "held",
    ))).scalar_one()
    diagnosis = diagnose_lease(status=row[0], expires_at=row[1])
    action, notes = recommend_recovery(
        diagnosis=diagnosis, unresolved_effects=unresolved,
        held_reservations=held, has_budget=budget is not None,
    )
    return ProductionOperationsView(
        quote_id=quote_id, story_id=quote, fulfillment_status=row[0],
        lease_diagnosis=diagnosis, lease_attempts=row[2],
        recovery_action=action, unresolved_effects=unresolved,
        held_reservations=held,
        budget_limit_micro_usd=budget[0] if budget else None,
        budget_held_micro_usd=budget[1] if budget else None,
        budget_spent_micro_usd=budget[2] if budget else None,
        notes=notes,
    )
