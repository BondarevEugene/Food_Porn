"""Conservative recovery for stories created before automatic AI budgets.

Never backfill books with existing production effects or queue jobs: their
historical financial exposure cannot be reconstructed from a new zero balance.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import book_budgets, budget_reservations
from app.little_legend.production_effect_ledger import production_effects
from app.little_legend.story_budget_provision import configured_book_budget_micro_usd


class BudgetRecoveryResult(BaseModel):
    scanned: int = Field(ge=0)
    created: int = Field(ge=0)
    skipped_financial_history: int = Field(ge=0)
    skipped_existing: int = Field(ge=0)
    dry_run: bool


def legacy_budget_is_safe(
    *, has_budget: bool, has_effect: bool,
    has_reservation: bool, has_writer_job: bool,
    has_illustration_job: bool,
) -> bool:
    return not any((
        has_budget, has_effect, has_reservation,
        has_writer_job, has_illustration_job,
    ))


async def recover_legacy_story_budgets(
    *, dry_run: bool = True, limit: int = 100,
    owner_id: int | None = None,
) -> BudgetRecoveryResult:
    """Recover up to limit oldest stories with no trace of AI activity.

    Must be invoked by trusted internal operations, never an unauthenticated
    request. Row locks serialize against new work and story deletion.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Recovery batch size must be 1..500")
    if owner_id is not None and (
        not isinstance(owner_id, int) or isinstance(owner_id, bool) or owner_id <= 0
    ):
        raise ValueError("Invalid owner filter")
    ceiling = configured_book_budget_micro_usd()
    from app.little_legend.illustration_queue_store import illustration_jobs
    from app.little_legend.router import stories
    from app.little_legend.writer_queue_store import writer_jobs

    async with async_session_maker() as session:
        query = select(stories.c.id, stories.c.owner_id).order_by(stories.c.id)
        if owner_id is not None:
            query = query.where(stories.c.owner_id == owner_id)
        rows = (await session.execute(
            query.limit(limit).with_for_update(skip_locked=True)
        )).all()
        created = skipped_history = skipped_existing = 0
        for story_id, story_owner in rows:
            has_budget = (await session.execute(select(exists().where(
                book_budgets.c.story_id == story_id,
            )))).scalar_one()
            if has_budget:
                skipped_existing += 1
                continue
            tables = (
                production_effects, budget_reservations,
                writer_jobs, illustration_jobs,
            )
            history = []
            for table in tables:
                history.append((await session.execute(select(exists().where(
                    table.c.story_id == story_id,
                )))).scalar_one())
            if not legacy_budget_is_safe(
                has_budget=False, has_effect=history[0],
                has_reservation=history[1], has_writer_job=history[2],
                has_illustration_job=history[3],
            ):
                skipped_history += 1
                continue
            if dry_run:
                created += 1
                continue
            result = await session.execute(
                pg_insert(book_budgets).values(
                    story_id=story_id, owner_id=story_owner,
                    limit_micro_usd=ceiling,
                    held_micro_usd=0, spent_micro_usd=0,
                    updated_at=datetime.now(UTC),
                ).on_conflict_do_nothing(index_elements=["story_id"])
                .returning(book_budgets.c.story_id)
            )
            if result.scalar_one_or_none() is not None:
                created += 1
            else:
                skipped_existing += 1
        if not dry_run:
            await session.commit()
    return BudgetRecoveryResult(
        scanned=len(rows), created=created,
        skipped_financial_history=skipped_history,
        skipped_existing=skipped_existing, dry_run=dry_run,
    )
