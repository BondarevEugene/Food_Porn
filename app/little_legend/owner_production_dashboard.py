"""Owner-scoped production overview for Little Legend release operations.

No privileged global watchdog data or child content crosses this boundary.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.production_watchdog import classify_fulfillment


class OrderHealth(BaseModel):
    quote_id: int = Field(gt=0)
    status: str
    alerts: list[str] = Field(default_factory=list)
    needs_attention: bool = False


class OwnerProductionDashboard(BaseModel):
    checked_at: datetime
    total_orders: int = Field(ge=0)
    attention_required: int = Field(ge=0)
    by_status: dict[str, int] = Field(default_factory=dict)
    orders: list[OrderHealth] = Field(default_factory=list)
    has_more: bool = False
    automatic_retry_allowed: bool = False


def build_dashboard(
    rows: list, *, now: datetime, limit: int = 50,
) -> OwnerProductionDashboard:
    """Pure formatter; only explicit owner-filtered rows may be supplied."""
    if not 1 <= limit <= 100:
        raise ValueError("Invalid dashboard limit")
    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    orders: list[OrderHealth] = []
    counts: Counter[str] = Counter()
    for row in rows[:limit]:
        quote_id, status, created_at, expires, delivery_start, delivered = row
        alerts = sorted(code.value for code in classify_fulfillment(
            status=status, created_at=created_at,
            lease_expires_at=expires, delivery_started_at=delivery_start,
            delivered_at=delivered, now=now,
        ))
        counts[status] += 1
        orders.append(OrderHealth(
            quote_id=quote_id, status=status, alerts=alerts,
            needs_attention=bool(alerts),
        ))
    return OwnerProductionDashboard(
        checked_at=now, total_orders=len(orders),
        attention_required=sum(item.needs_attention for item in orders),
        by_status=dict(counts), orders=orders, has_more=len(rows) > limit,
    )


async def inspect_owner_dashboard(
    *, owner_id: int, limit: int = 50,
) -> OwnerProductionDashboard:
    if owner_id <= 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid owner or limit")
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(
                fulfillment_jobs.c.quote_id,
                fulfillment_jobs.c.status,
                fulfillment_jobs.c.created_at,
                fulfillment_jobs.c.lease_expires_at,
                fulfillment_jobs.c.delivery_started_at,
                fulfillment_jobs.c.delivered_at,
            )
            .join(
                order_quotes,
                (order_quotes.c.id == fulfillment_jobs.c.quote_id)
                & (order_quotes.c.owner_id == fulfillment_jobs.c.owner_id),
            )
            .where(fulfillment_jobs.c.owner_id == owner_id)
            .order_by(
                fulfillment_jobs.c.created_at.desc(),
                fulfillment_jobs.c.quote_id.desc(),
            )
            .limit(limit + 1)
        )).all()
    return build_dashboard(rows, now=datetime.now(UTC), limit=limit)
