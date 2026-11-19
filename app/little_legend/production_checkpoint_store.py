"""Persist Little Legend production checkpoints in PostgreSQL.

Optimistic compare-and-swap prevents stale workers from overwriting progress.
The database enforces one checkpoint per story and cascading deletion.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, MetaData,
    String, Table, select, update,
)

from app.database.session import async_session_maker
from app.little_legend.production_checkpoint import (
    ProductionCheckpoint, ProductionPhase, advance_checkpoint,
)

metadata = MetaData()
production_checkpoints = Table(
    "little_legend_production_checkpoints", metadata,
    Column("story_id", Integer, ForeignKey(
        "little_legend_stories.id", ondelete="CASCADE",
    ), primary_key=True),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("phase", String(32), nullable=False, index=True),
    Column("release_fingerprint", String(64), nullable=True),
    Column("pdf_sha256", String(64), nullable=True),
    Column("delivery_message_id", BigInteger, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _decode(row) -> ProductionCheckpoint:
    return ProductionCheckpoint.model_validate(dict(row))


async def create_checkpoint(
    *, owner_id: int, story_id: int,
) -> ProductionCheckpoint:
    """Idempotent creation; never return a checkpoint belonging to another owner."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(UTC)
    async with async_session_maker() as session:
        await session.execute(
            pg_insert(production_checkpoints).values(
                story_id=story_id, owner_id=owner_id, version=0,
                phase=ProductionPhase.DRAFT.value, updated_at=now,
            ).on_conflict_do_nothing(index_elements=["story_id"])
        )
        row = (await session.execute(select(production_checkpoints).where(
            production_checkpoints.c.story_id == story_id,
            production_checkpoints.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        if row is None:
            raise PermissionError("Story checkpoint not found")
        await session.commit()
        return _decode(row)


async def get_checkpoint(
    *, owner_id: int, story_id: int,
) -> ProductionCheckpoint | None:
    async with async_session_maker() as session:
        row = (await session.execute(select(production_checkpoints).where(
            production_checkpoints.c.story_id == story_id,
            production_checkpoints.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        return _decode(row) if row is not None else None


async def persist_transition(
    *, owner_id: int, story_id: int, expected_version: int,
    next_phase: ProductionPhase, release_fingerprint: str | None = None,
    pdf_sha256: str | None = None, delivery_message_id: int | None = None,
) -> ProductionCheckpoint:
    """Atomically validate and commit one phase transition."""
    async with async_session_maker() as session:
        row = (await session.execute(select(production_checkpoints).where(
            production_checkpoints.c.story_id == story_id,
            production_checkpoints.c.owner_id == owner_id,
        ).with_for_update())).mappings().one_or_none()
        if row is None:
            raise PermissionError("Story checkpoint not found")
        advanced = advance_checkpoint(
            _decode(row), expected_version=expected_version,
            next_phase=next_phase, release_fingerprint=release_fingerprint,
            pdf_sha256=pdf_sha256, delivery_message_id=delivery_message_id,
        )
        result = await session.execute(update(production_checkpoints).where(
            production_checkpoints.c.story_id == story_id,
            production_checkpoints.c.owner_id == owner_id,
            production_checkpoints.c.version == expected_version,
        ).values(
            version=advanced.version, phase=advanced.phase.value,
            release_fingerprint=advanced.release_fingerprint,
            pdf_sha256=advanced.pdf_sha256,
            delivery_message_id=advanced.delivery_message_id,
            updated_at=advanced.updated_at,
        ))
        if result.rowcount != 1:
            raise PermissionError("Stale production checkpoint version")
        await session.commit()
        return advanced


async def list_unfinished_checkpoints(
    *, owner_id: int, limit: int = 50,
) -> list[ProductionCheckpoint]:
    """Owner-scoped recovery candidates, not permission to repeat paid calls."""
    if not 1 <= limit <= 100:
        raise ValueError("Invalid recovery page size")
    async with async_session_maker() as session:
        rows = (await session.execute(select(production_checkpoints).where(
            production_checkpoints.c.owner_id == owner_id,
            production_checkpoints.c.phase != ProductionPhase.DELIVERED.value,
        ).order_by(
            production_checkpoints.c.updated_at,
            production_checkpoints.c.story_id,
        ).limit(limit))).mappings().all()
        return [_decode(row) for row in rows]
