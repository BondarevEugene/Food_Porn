"""Fail-closed Little Legend payment entitlement checks.

A quote is only a price snapshot. Production must check a verified receipt
bound to that quote; neither a client status nor a checkout redirect suffices.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()
receipts = Table(
    "little_legend_payment_receipts",
    metadata,
    Column("quote_id", BigInteger, ForeignKey("little_legend_order_quotes.id"), primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column("provider", String(32), nullable=False),
    Column("provider_reference", String(120), nullable=False, unique=True),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("verified_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class PaymentEvidence:
    """Server-verified receipt data, never accepted from a public request body."""

    quote_id: int
    owner_id: int
    provider: str
    provider_reference: str
    amount_minor: int
    currency: str


def evidence_matches_quote(evidence: PaymentEvidence, quote: dict) -> bool:
    """Reject wrong owner, amount, currency, edition or non-payable quote."""
    return (
        evidence.quote_id > 0
        and evidence.owner_id > 0
        and evidence.provider == "wayforpay"
        and bool(evidence.provider_reference.strip())
        and evidence.quote_id == quote.get("id")
        and evidence.owner_id == quote.get("owner_id")
        and evidence.amount_minor == quote.get("price_minor")
        and evidence.currency == quote.get("currency") == "UAH"
        and quote.get("edition") == "digital"
        and quote.get("status") == "quoted"
    )


async def has_verified_entitlement(
    session: AsyncSession, *, quote_id: int, owner_id: int
) -> bool:
    """Check a durable receipt, including exact price and owner match."""
    if quote_id <= 0 or owner_id <= 0:
        return False
    from app.little_legend.order_quotes import order_quotes

    row = (
        await session.execute(
            select(
                order_quotes.c.id,
                order_quotes.c.owner_id,
                order_quotes.c.edition,
                order_quotes.c.currency,
                order_quotes.c.price_minor,
                order_quotes.c.status,
                receipts.c.provider,
                receipts.c.provider_reference,
                receipts.c.amount_minor,
                receipts.c.currency.label("receipt_currency"),
            )
            .join(receipts, receipts.c.quote_id == order_quotes.c.id)
            .where(
                order_quotes.c.id == quote_id,
                order_quotes.c.owner_id == owner_id,
                receipts.c.owner_id == owner_id,
            )
        )
    ).mappings().one_or_none()
    if row is None:
        return False
    return evidence_matches_quote(
        PaymentEvidence(
            quote_id=row["id"],
            owner_id=row["owner_id"],
            provider=row["provider"],
            provider_reference=row["provider_reference"],
            amount_minor=row["amount_minor"],
            currency=row["receipt_currency"],
        ),
        dict(row),
    )
