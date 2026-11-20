"""Read-only production watchdog for Little Legend.

Uses metadata only. Never reclaims leases, retries AI, resends Telegram,
releases held budgets, or logs customer identifiers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import book_budgets, budget_reservations
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.production_effect_ledger import production_effects


class AlertCode(StrEnum):
    STALE_PDF_LEASE = "stale_pdf_lease"
    DELIVERY_UNCONFIRMED = "delivery_unconfirmed"
    BLOCKED_FULFILLMENT = "blocked_fulfillment"
    OLD_PENDING = "old_pending"
    UNRESOLVED_AI_EFFECTS = "unresolved_ai_effects"
    HELD_AI_BUDGET = "held_ai_budget"
    BUDGET_OVERCOMMITTED = "budget_overcommitted"


class WatchdogReport(BaseModel):
    checked_at: datetime
    total_fulfillment_jobs: int = Field(ge=0)
    alerts: dict[str, int] = Field(default_factory=dict)
    requires_operator: bool = False
    automatic_retry_allowed: bool = False


def classify_fulfillment(
    *, status: str, created_at: datetime,
    lease_expires_at: datetime | None,
    delivery_started_at: datetime | None,
    delivered_at: datetime | None,
    now: datetime, pending_minutes: int = 60,
) -> set[AlertCode]:
    """Classify a single job; timestamps must be timezone-aware."""
    if pending_minutes < 1:
        raise ValueError("pending_minutes must be positive")
    if any(value.tzinfo is None for value in (
        now, created_at, *(
            item for item in (
                lease_expires_at, delivery_started_at, delivered_at,
            ) if item is not None
        ),
    )):
        raise ValueError("Watchdog requires timezone-aware timestamps")
    codes: set[AlertCode] = set()
    if status == "processing" and (
        lease_expires_at is None or lease_expires_at <= now
    ):
        codes.add(AlertCode.STALE_PDF_LEASE)
    if delivery_started_at is not None and delivered_at is None:
        codes.add(AlertCode.DELIVERY_UNCONFIRMED)
    if status in {"blocked", "failed"}:
        codes.add(AlertCode.BLOCKED_FULFILLMENT)
    if status == "pending" and created_at <= now - timedelta(minutes=pending_minutes):
        codes.add(AlertCode.OLD_PENDING)
    return codes


def budget_overcommitted(
    *, limit_micro_usd: int, held_micro_usd: int, spent_micro_usd: int,
) -> bool:
    if min(limit_micro_usd, held_micro_usd, spent_micro_usd) < 0:
        return True
    return held_micro_usd + spent_micro_usd > limit_micro_usd


async def inspect_watchdog(
    *, now: datetime | None = None, pending_minutes: int = 60,
) -> WatchdogReport:
    """Aggregate counts from Neon; never return quote, owner or story IDs."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not 1 <= pending_minutes <= 10080:
        raise ValueError("pending_minutes out of range")
    async with async_session_maker() as session:
        total = await session.scalar(select(func.count()).select_from(fulfillment_jobs))
        stale = await session.scalar(select(func.count()).select_from(
            fulfillment_jobs,
        ).where(
            fulfillment_jobs.c.status == "processing",
            (fulfillment_jobs.c.lease_expires_at.is_(None))
            | (fulfillment_jobs.c.lease_expires_at <= now),
        ))
        delivery = await session.scalar(select(func.count()).select_from(
            fulfillment_jobs,
        ).where(
            fulfillment_jobs.c.delivery_started_at.is_not(None),
            fulfillment_jobs.c.delivered_at.is_(None),
        ))
        blocked = await session.scalar(select(func.count()).select_from(
            fulfillment_jobs,
        ).where(fulfillment_jobs.c.status.in_(("blocked", "failed"))))
        pending = await session.scalar(select(func.count()).select_from(
            fulfillment_jobs,
        ).where(
            fulfillment_jobs.c.status == "pending",
            fulfillment_jobs.c.created_at <= now - timedelta(minutes=pending_minutes),
        ))
        effects = await session.scalar(select(func.count()).select_from(
            production_effects,
        ).where(production_effects.c.status.in_((
            "reserved", "dispatched", "uncertain",
        ))))
        held = await session.scalar(select(func.count()).select_from(
            budget_reservations,
        ).where(budget_reservations.c.status == "held"))
        budgets = (await session.execute(select(
            book_budgets.c.limit_micro_usd,
            book_budgets.c.held_micro_usd,
            book_budgets.c.spent_micro_usd,
        ))).all()
    counts = Counter({
        AlertCode.STALE_PDF_LEASE.value: int(stale or 0),
        AlertCode.DELIVERY_UNCONFIRMED.value: int(delivery or 0),
        AlertCode.BLOCKED_FULFILLMENT.value: int(blocked or 0),
        AlertCode.OLD_PENDING.value: int(pending or 0),
        AlertCode.UNRESOLVED_AI_EFFECTS.value: int(effects or 0),
        AlertCode.HELD_AI_BUDGET.value: int(held or 0),
        AlertCode.BUDGET_OVERCOMMITTED.value: sum(
            budget_overcommitted(
                limit_micro_usd=limit,
                held_micro_usd=held_amount,
                spent_micro_usd=spent,
            )
            for limit, held_amount, spent in budgets
        ),
    })
    return WatchdogReport(
        checked_at=now,
        total_fulfillment_jobs=int(total or 0),
        alerts=dict(counts),
        requires_operator=any(counts.values()),
    )


async def run() -> int:
    report = await inspect_watchdog()
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    return 2 if report.requires_operator else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Little Legend watchdog")
    parser.parse_args(argv)
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
