"""Single-transaction AI dispatch authorization.

Budget, effect identity, and dispatch marker are committed together before
a billable provider request. This function NEVER calls an AI provider.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import (
    BookBudget,
    BudgetReservationStatus,
    available_micro_usd,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
    production_effects,
)


class DispatchAuthorization(BaseModel):
    effect_key: str
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    reserved_micro_usd: int = Field(gt=0)
    authorized: bool = False


async def authorize_ai_dispatch(
    *, owner_id: int, story_id: int, effect_key: str,
    kind: EffectKind, request_sha256: str,
    estimated_micro_usd: int,
) -> DispatchAuthorization:
    """Return authorized=True only for a newly committed dispatch fence.

    A repeated call for the same effect never authorizes a second dispatch.
    """
    if kind not in {EffectKind.WRITER_AI, EffectKind.ILLUSTRATION_AI}:
        raise ValueError("Only paid AI effects may use AI budget")
    if not isinstance(estimated_micro_usd, int) or isinstance(
        estimated_micro_usd, bool,
    ) or estimated_micro_usd <= 0:
        raise ValueError("Positive integer estimated cost required")
    now = datetime.now(UTC)
    candidate = ProductionEffect(
        effect_key=effect_key, owner_id=owner_id, story_id=story_id,
        kind=kind, request_sha256=request_sha256,
        created_at=now, updated_at=now,
    )
    async with async_session_maker() as session:
        budget_row = (await session.execute(select(book_budgets).where(
            book_budgets.c.owner_id == owner_id,
            book_budgets.c.story_id == story_id,
        ).with_for_update())).mappings().one_or_none()
        if budget_row is None:
            raise PermissionError("Book AI budget not configured")
        budget = BookBudget.model_validate(dict(budget_row))
        inserted = (await session.execute(
            pg_insert(production_effects).values(
                **candidate.model_dump(mode="python"),
            ).on_conflict_do_nothing(index_elements=["effect_key"])
            .returning(production_effects.c.effect_key)
        )).scalar_one_or_none()
        if inserted is None:
            previous = (await session.execute(select(production_effects).where(
                production_effects.c.effect_key == effect_key,
            ))).mappings().one()
            if (
                previous["owner_id"] != owner_id
                or previous["story_id"] != story_id
                or previous["kind"] != kind.value
                or previous["request_sha256"] != request_sha256
            ):
                raise PermissionError("Idempotency key collision")
            return DispatchAuthorization(
                effect_key=effect_key, owner_id=owner_id,
                story_id=story_id, reserved_micro_usd=estimated_micro_usd,
            )
        if available_micro_usd(budget) < estimated_micro_usd:
            raise PermissionError("Book AI budget exceeded")
        await session.execute(pg_insert(budget_reservations).values(
            effect_key=effect_key, owner_id=owner_id, story_id=story_id,
            reserved_micro_usd=estimated_micro_usd,
            status=BudgetReservationStatus.HELD.value,
            updated_at=now,
        ))
        await session.execute(update(book_budgets).where(
            book_budgets.c.story_id == story_id,
            book_budgets.c.owner_id == owner_id,
        ).values(
            held_micro_usd=budget.held_micro_usd + estimated_micro_usd,
            updated_at=now,
        ))
        await session.execute(update(production_effects).where(
            production_effects.c.effect_key == effect_key,
            production_effects.c.status == EffectStatus.RESERVED.value,
        ).values(
            status=EffectStatus.DISPATCHED.value,
            updated_at=now,
        ))
        await session.commit()
        return DispatchAuthorization(
            effect_key=effect_key, owner_id=owner_id, story_id=story_id,
            reserved_micro_usd=estimated_micro_usd, authorized=True,
        )
