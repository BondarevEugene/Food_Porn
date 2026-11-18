"""Append-only AI cost receipts; never infer charges from dispatch alone."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    insert,
    select,
)

from app.database.session import async_session_maker
from app.little_legend.writer_queue_store import writer_jobs


class CostEvidence(StrEnum):
    PROVIDER_RECEIPT = "provider_receipt"
    PROVIDER_INVOICE = "provider_invoice"


class CostReceipt(BaseModel):
    receipt_id: str = Field(min_length=8, max_length=120)
    job_id: str = Field(min_length=8, max_length=120)
    provider: str = Field(min_length=1, max_length=100)
    provider_reference: str = Field(min_length=1, max_length=200)
    amount_usd: Decimal
    evidence: CostEvidence

    @field_validator("amount_usd")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        try:
            if not value.is_finite() or value < 0 or value > Decimal("100"):
                raise ValueError("Invalid confirmed USD amount")
            if value.as_tuple().exponent < -6:
                raise ValueError("USD amount supports at most six decimals")
        except InvalidOperation as exc:
            raise ValueError("Invalid USD amount") from exc
        return value


ledger_metadata = MetaData()
cost_receipts = Table(
    "little_legend_ai_cost_receipts",
    ledger_metadata,
    Column("receipt_id", String(120), primary_key=True),
    Column("job_id", String(120), ForeignKey(writer_jobs.c.job_id), nullable=False),
    Column("owner_id", BigInteger, nullable=False),
    Column("story_id", Integer, nullable=False),
    Column("provider", String(100), nullable=False),
    Column("provider_reference", String(200), nullable=False, unique=True),
    Column("amount_usd", Numeric(12, 6), nullable=False),
    Column("evidence", String(30), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)


async def record_confirmed_cost(
    receipt: CostReceipt, *, owner_id: int, story_id: int,
) -> bool:
    """Insert one verified provider charge, idempotently by provider reference.

    Trusted internal operator function; no public route or auto-retry.
    False means identical evidence already recorded; conflicts fail closed.
    """
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid ownership scope")
    async with async_session_maker() as session:
        job = (await session.execute(
            select(writer_jobs.c.job_id).where(
                writer_jobs.c.job_id == receipt.job_id,
                writer_jobs.c.owner_id == owner_id,
                writer_jobs.c.story_id == story_id,
            )
        )).scalar_one_or_none()
        if job is None:
            raise PermissionError("Cost receipt does not belong to story owner")
        existing = (await session.execute(
            select(cost_receipts).where(
                cost_receipts.c.provider == receipt.provider,
                cost_receipts.c.provider_reference == receipt.provider_reference,
            )
        )).mappings().one_or_none()
        if existing is not None:
            if (
                existing["job_id"] == receipt.job_id
                and existing["owner_id"] == owner_id
                and existing["story_id"] == story_id
                and existing["amount_usd"] == receipt.amount_usd
                and existing["evidence"] == receipt.evidence.value
            ):
                return False
            raise ValueError("Conflicting provider cost evidence")
        await session.execute(insert(cost_receipts).values(
            receipt_id=receipt.receipt_id,
            job_id=receipt.job_id, owner_id=owner_id, story_id=story_id,
            provider=receipt.provider,
            provider_reference=receipt.provider_reference,
            amount_usd=receipt.amount_usd, evidence=receipt.evidence.value,
            recorded_at=datetime.now(UTC),
        ))
        await session.commit()
    return True
