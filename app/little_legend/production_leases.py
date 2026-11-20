"""Production lease lifecycle for paid Little Legend fulfillment.

A lease coordinates *one* worker. Expired processing is never automatically
reclaimed: a crash may have already consumed AI budget or written an asset.
Operator reconciliation must establish safety before any new attempt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.payment_entitlement import has_verified_entitlement

DEFAULT_LEASE_SECONDS = 180


class ProductionState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    BLOCKED = "blocked"


class LeaseDiagnosis(StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    STALE_REVIEW = "stale_review"
    READY = "ready"
    FAILED_REVIEW = "failed_review"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ProductionLease:
    quote_id: int
    owner_id: int
    token: str
    expires_at: datetime
    attempt: int


def diagnose_lease(*, status: str, expires_at: datetime | None,
                   now: datetime | None = None) -> LeaseDiagnosis:
    """Classify a job without issuing new work or touching payment state."""
    now = now or datetime.now(UTC)
    if status == ProductionState.PENDING:
        return LeaseDiagnosis.QUEUED
    if status == ProductionState.READY:
        return LeaseDiagnosis.READY
    if status == ProductionState.BLOCKED:
        return LeaseDiagnosis.BLOCKED
    if status == ProductionState.FAILED:
        return LeaseDiagnosis.FAILED_REVIEW
    if status == ProductionState.PROCESSING:
        if expires_at is None or expires_at <= now:
            return LeaseDiagnosis.STALE_REVIEW
        return LeaseDiagnosis.ACTIVE
    raise ValueError("Unknown production state")


def _duration(seconds: int) -> timedelta:
    if isinstance(seconds, bool) or not 30 <= seconds <= 3600:
        raise ValueError("Lease duration must be between 30 and 3600 seconds")
    return timedelta(seconds=seconds)


async def claim_pending(
    session: AsyncSession, *, quote_id: int, owner_id: int,
    seconds: int = DEFAULT_LEASE_SECONDS,
) -> ProductionLease | None:
    """Atomically claim *pending* paid work; never steal an expired lease.

    Caller commits the surrounding transaction before invoking external work.
    A returned lease is not permission to bypass consent, budgets or quality.
    """
    duration = _duration(seconds)
    if quote_id <= 0 or owner_id <= 0:
        raise ValueError("Invalid fulfillment identity")
    if not await has_verified_entitlement(
        session, quote_id=quote_id, owner_id=owner_id,
    ):
        raise PermissionError("Verified payment required")
    now = datetime.now(UTC)
    token = str(uuid4())
    row = (await session.execute(
        update(fulfillment_jobs).where(
            fulfillment_jobs.c.quote_id == quote_id,
            fulfillment_jobs.c.owner_id == owner_id,
            fulfillment_jobs.c.status == ProductionState.PENDING.value,
            fulfillment_jobs.c.lease_token.is_(None),
        ).values(
            status=ProductionState.PROCESSING.value,
            lease_token=token,
            lease_expires_at=now + duration,
            lease_attempts=fulfillment_jobs.c.lease_attempts + 1,
            updated_at=now,
        ).returning(
            fulfillment_jobs.c.lease_attempts,
        )
    )).scalar_one_or_none()
    if row is None:
        return None
    return ProductionLease(quote_id, owner_id, token, now + duration, row)


async def heartbeat(
    session: AsyncSession, *, lease: ProductionLease,
    seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Extend only the current, unexpired lease; old workers cannot revive it."""
    duration = _duration(seconds)
    now = datetime.now(UTC)
    result = await session.execute(
        update(fulfillment_jobs).where(
            fulfillment_jobs.c.quote_id == lease.quote_id,
            fulfillment_jobs.c.owner_id == lease.owner_id,
            fulfillment_jobs.c.status == ProductionState.PROCESSING.value,
            fulfillment_jobs.c.lease_token == lease.token,
            fulfillment_jobs.c.lease_expires_at > now,
        ).values(lease_expires_at=now + duration, updated_at=now)
        .returning(fulfillment_jobs.c.quote_id)
    )
    return result.scalar_one_or_none() is not None


async def finish_processing(
    session: AsyncSession, *, lease: ProductionLease, succeeded: bool,
) -> bool:
    """Terminal transition only for the current unexpired owner.

    The caller must verify the finished private asset and quality gates
    before marking succeeded=True. Never sends Telegram or charges a card.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        update(fulfillment_jobs).where(
            fulfillment_jobs.c.quote_id == lease.quote_id,
            fulfillment_jobs.c.owner_id == lease.owner_id,
            fulfillment_jobs.c.status == ProductionState.PROCESSING.value,
            fulfillment_jobs.c.lease_token == lease.token,
            fulfillment_jobs.c.lease_expires_at > now,
        ).values(
            status=(ProductionState.READY if succeeded else ProductionState.FAILED).value,
            lease_token=None,
            lease_expires_at=None,
            updated_at=now,
        ).returning(fulfillment_jobs.c.quote_id)
    )
    return result.scalar_one_or_none() is not None


async def inspect_job(
    session: AsyncSession, *, quote_id: int, owner_id: int,
) -> tuple[LeaseDiagnosis, int] | None:
    """Owner-scoped, metadata-only diagnosis. No private child content."""
    row = (await session.execute(select(
        fulfillment_jobs.c.status, fulfillment_jobs.c.lease_expires_at,
        fulfillment_jobs.c.lease_attempts,
    ).where(
        fulfillment_jobs.c.quote_id == quote_id,
        fulfillment_jobs.c.owner_id == owner_id,
    ))).one_or_none()
    if row is None:
        return None
    return diagnose_lease(status=row[0], expires_at=row[1]), row[2]
