"""Persistent price snapshot. A quote is NEVER a payment entitlement."""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.session import async_session_maker
from app.little_legend.commercial_catalog import BookEdition, crm_book_catalog

metadata = MetaData()
order_quotes = Table(
    "little_legend_order_quotes", metadata,
    Column("id", BigInteger, primary_key=True),
    Column("story_id", Integer, ForeignKey("little_legend_stories.id", ondelete="CASCADE"), nullable=False),
    Column("owner_id", BigInteger, nullable=False),
    Column("edition", String(16), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("price_minor", BigInteger, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class BookOrderQuote(BaseModel):
    id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    owner_id: int = Field(gt=0)
    edition: BookEdition
    currency: str = "UAH"
    price_minor: int = Field(gt=0)
    status: str = "quoted"
    payment_enabled: bool = False
    production_enabled: bool = False
    created_at: datetime


async def create_order_quote(*, owner_id: int, story_id: int, edition: BookEdition) -> BookOrderQuote:
    """Freeze the first configured price; retries cannot silently reprice it."""
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid owner or story")
    if edition != BookEdition.DIGITAL:
        raise PermissionError("print_production_not_certified")
    catalog = await crm_book_catalog()
    offer = next(item for item in catalog.offers if item.edition == edition)
    if not offer.available or offer.price_minor is None:
        raise PermissionError("price_not_configured")
    from app.little_legend.router import stories

    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if owned is None:
            raise PermissionError("Story not found")
        await session.execute(pg_insert(order_quotes).values(
            story_id=story_id, owner_id=owner_id,
            edition=edition.value, currency="UAH",
            price_minor=offer.price_minor, status="quoted",
            created_at=datetime.now(UTC),
        ).on_conflict_do_nothing(constraint="uq_ll_quote_story_edition"))
        row = (await session.execute(select(order_quotes).where(
            order_quotes.c.story_id == story_id,
            order_quotes.c.owner_id == owner_id,
            order_quotes.c.edition == edition.value,
        ))).mappings().one()
        await session.commit()
        return BookOrderQuote.model_validate(dict(row))
