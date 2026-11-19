"""Transactional per-book AI spending guard.

All money is stored as integer micro-USD. A dispatch reservation holds budget
until provider reconciliation; unknown charges are never released automatically.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.session import async_session_maker


class BudgetReservationStatus(StrEnum):
    HELD = "held"
    SETTLED = "settled"
    RELEASED = "released"


metadata = MetaData()
book_budgets = Table(
    "little_legend_book_budgets", metadata,
    Column(
        "story_id", Integer,
        ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("limit_micro_usd", BigInteger, nullable=False),
    Column("held_micro_usd", BigInteger, nullable=False),
    Column("spent_micro_usd", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
budget_reservations = Table(
    "little_legend_budget_reservations", metadata,
    Column("effect_key", String(120), primary_key=True),
    Column(
        "story_id", Integer,
        ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    ),
    Column("owner_id", BigInteger, nullable=False),
    Column("reserved_micro_usd", BigInteger, nullable=False),
    Column("actual_micro_usd", BigInteger, nullable=True),
    Column("status", String(16), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class BookBudget(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    limit_micro_usd: int = Field(ge=0)
    held_micro_usd: int = Field(ge=0)
    spent_micro_usd: int = Field(ge=0)


def available_micro_usd(budget: BookBudget) -> int:
    return budget.limit_micro_usd - budget.held_micro_usd - budget.spent_micro_usd


def _validate_amount(amount: int) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("Positive integer micro-USD amount required")


async def configure_book_budget(
    *, owner_id: int, story_id: int, limit_micro_usd: int,
) -> BookBudget:
    """Create once; existing budget cannot silently be reset."""
    _validate_amount(limit_micro_usd)
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Positive owner and story IDs required")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        from app.little_legend.router import stories

        # Serialize ownership validation with story deletion and updates.
        owned_story = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id,
            stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if owned_story is None:
            raise PermissionError("Story does not belong to budget owner")
        await session.execute(pg_insert(book_budgets).values(
            story_id=story_id, owner_id=owner_id,
            limit_micro_usd=limit_micro_usd,
            held_micro_usd=0, spent_micro_usd=0, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["story_id"]))
        row = (await session.execute(select(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        if row is None or row["limit_micro_usd"] != limit_micro_usd:
            raise PermissionError("Budget missing or configured differently")
        await session.commit()
        return BookBudget.model_validate(dict(row))


async def reserve_ai_budget(
    *, owner_id: int, story_id: int, effect_key: str,
    amount_micro_usd: int,
) -> bool:
    """Atomically reserve once; False means this effect already has a hold."""
    _validate_amount(amount_micro_usd)
    if not 8 <= len(effect_key) <= 120:
        raise ValueError("Invalid effect key")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        budget_row = (await session.execute(select(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if budget_row is None:
            raise PermissionError("Book budget not configured")
        prior = (await session.execute(select(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
        ))).mappings().one_or_none()
        if prior is not None:
            if (
                prior["owner_id"] != owner_id
                or prior["story_id"] != story_id
                or prior["reserved_micro_usd"] != amount_micro_usd
            ):
                raise PermissionError("Budget effect key reused")
            return False
        budget = BookBudget.model_validate(dict(budget_row))
        if available_micro_usd(budget) < amount_micro_usd:
            raise PermissionError("Book AI budget exceeded")
        await session.execute(pg_insert(budget_reservations).values(
            effect_key=effect_key, owner_id=owner_id, story_id=story_id,
            reserved_micro_usd=amount_micro_usd,
            status=BudgetReservationStatus.HELD.value, updated_at=now,
        ))
        await session.execute(update(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).values(
            held_micro_usd=budget.held_micro_usd + amount_micro_usd,
            updated_at=now,
        ))
        await session.commit()
        return True


async def settle_ai_budget(
    *, owner_id: int, story_id: int, effect_key: str,
    actual_micro_usd: int,
) -> BookBudget:
    """Settle only a held reservation; never settle above its ceiling."""
    if not isinstance(actual_micro_usd, int) or isinstance(
        actual_micro_usd, bool,
    ) or actual_micro_usd < 0:
        raise ValueError("Invalid actual cost")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        budget_row = (await session.execute(select(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if budget_row is None:
            raise PermissionError("Book budget not found")
        reservation = (await session.execute(select(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
            budget_reservations.c.story_id == story_id,
            budget_reservations.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if reservation is None or reservation["status"] != "held":
            raise PermissionError("No active budget reservation")
        reserved = reservation["reserved_micro_usd"]
        if actual_micro_usd > reserved:
            raise PermissionError("Actual charge exceeds reserved ceiling")
        budget = BookBudget.model_validate(dict(budget_row))
        changed = budget.model_copy(update={
            "held_micro_usd": budget.held_micro_usd - reserved,
            "spent_micro_usd": budget.spent_micro_usd + actual_micro_usd,
        })
        await session.execute(update(budget_reservations).where(
            budget_reservations.c.effect_key == effect_key,
        ).values(
            status=BudgetReservationStatus.SETTLED.value,
            actual_micro_usd=actual_micro_usd, updated_at=now,
        ))
        await session.execute(update(book_budgets).where(
            book_budgets.c.story_id == story_id,
        ).values(
            held_micro_usd=changed.held_micro_usd,
            spent_micro_usd=changed.spent_micro_usd,
            updated_at=now,
        ))
        await session.commit()
        return changed


async def get_book_budget(
    *, owner_id: int, story_id: int,
) -> BookBudget | None:
    async with async_session_maker() as session:
        row = (await session.execute(select(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        return BookBudget.model_validate(dict(row)) if row else None
