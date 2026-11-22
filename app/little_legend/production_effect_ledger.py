"""Durable idempotency ledger for production side effects.

A reservation is committed BEFORE any external provider call. An ambiguous
outcome is never retried automatically; it requires explicit reconciliation.
"""
from __future__ import annotations

import hashlib
import json
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


class EffectStatus(StrEnum):
    RESERVED = "reserved"
    DISPATCHED = "dispatched"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


class EffectKind(StrEnum):
    WRITER_AI = "writer_ai"
    ILLUSTRATION_AI = "illustration_ai"
    TELEGRAM_PDF = "telegram_pdf"
    TELEGRAM_AUTO_REQUEST = "telegram_auto_request"


metadata = MetaData()
production_effects = Table(
    "little_legend_production_effects", metadata,
    Column("effect_key", String(120), primary_key=True),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column(
        "story_id", Integer,
        ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    ),
    Column("kind", String(32), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("status", String(24), nullable=False, index=True),
    Column("provider_reference", String(160), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class ProductionEffect(BaseModel):
    effect_key: str = Field(min_length=8, max_length=120)
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    kind: EffectKind
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: EffectStatus = EffectStatus.RESERVED
    provider_reference: str | None = Field(default=None, max_length=160)
    created_at: datetime
    updated_at: datetime


def request_fingerprint(payload: dict) -> str:
    """Stable request identity; store only the digest, never child content."""
    data = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _decode(row) -> ProductionEffect:
    return ProductionEffect.model_validate(dict(row))


async def reserve_effect(
    *, effect_key: str, owner_id: int, story_id: int,
    kind: EffectKind, request_sha256: str,
) -> tuple[ProductionEffect, bool]:
    """Create once; a repeated key returns its existing immutable reservation."""
    now = datetime.now(UTC)
    candidate = ProductionEffect(
        effect_key=effect_key, owner_id=owner_id, story_id=story_id,
        kind=kind, request_sha256=request_sha256,
        created_at=now, updated_at=now,
    )
    async with async_session_maker() as session:
        from app.little_legend.router import stories

        owned_story = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id,
            stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if owned_story is None:
            raise PermissionError("Story does not belong to effect owner")
        result = await session.execute(
            pg_insert(production_effects).values(
                **candidate.model_dump(mode="python"),
            ).on_conflict_do_nothing(index_elements=["effect_key"])
            .returning(production_effects.c.effect_key)
        )
        created = result.scalar_one_or_none() is not None
        row = (await session.execute(select(production_effects).where(
            production_effects.c.effect_key == effect_key,
            production_effects.c.owner_id == owner_id,
            production_effects.c.story_id == story_id,
        ))).mappings().one_or_none()
        if row is None:
            raise PermissionError("Production effect not found")
        effect = _decode(row)
        if effect.kind != kind or effect.request_sha256 != request_sha256:
            raise PermissionError("Idempotency key reused for different request")
        await session.commit()
        return effect, created


async def transition_effect(
    *, effect_key: str, owner_id: int, story_id: int,
    expected_status: EffectStatus, next_status: EffectStatus,
    provider_reference: str | None = None,
) -> ProductionEffect:
    """Commit a legal transition atomically, fencing stale workers."""
    allowed = {
        EffectStatus.RESERVED: {EffectStatus.DISPATCHED},
        EffectStatus.DISPATCHED: {
            EffectStatus.CONFIRMED, EffectStatus.UNCERTAIN,
        },
        EffectStatus.UNCERTAIN: {EffectStatus.CONFIRMED},
    }
    if next_status not in allowed.get(expected_status, set()):
        raise PermissionError("Invalid production effect transition")
    if next_status == EffectStatus.CONFIRMED and not provider_reference:
        raise ValueError("Provider acknowledgement is required")
    if provider_reference is not None and len(provider_reference) > 160:
        raise ValueError("Provider reference too long")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        result = await session.execute(
            update(production_effects).where(
                production_effects.c.effect_key == effect_key,
                production_effects.c.owner_id == owner_id,
                production_effects.c.story_id == story_id,
                production_effects.c.status == expected_status.value,
            ).values(
                status=next_status.value,
                provider_reference=provider_reference,
                updated_at=now,
            ).returning(production_effects)
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise PermissionError("Stale or foreign production effect")
        await session.commit()
        return _decode(row)


async def list_unresolved_effects(
    *, owner_id: int, limit: int = 50,
) -> list[ProductionEffect]:
    """Recovery candidates only; this never triggers external side effects."""
    if not 1 <= limit <= 100:
        raise ValueError("Invalid recovery page size")
    async with async_session_maker() as session:
        rows = (await session.execute(select(production_effects).where(
            production_effects.c.owner_id == owner_id,
            production_effects.c.status != EffectStatus.CONFIRMED.value,
        ).order_by(
            production_effects.c.created_at,
            production_effects.c.effect_key,
        ).limit(limit))).mappings().all()
    return [_decode(row) for row in rows]


async def list_pending_auto_delivery(*, limit: int = 20) -> list[ProductionEffect]:
    """Read opted-in pending deliveries; the PDF ledger fences concurrent workers."""
    if not 1 <= limit <= 100:
        raise ValueError("Invalid auto-delivery batch size")
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(production_effects).where(
                production_effects.c.kind == EffectKind.TELEGRAM_AUTO_REQUEST.value,
                production_effects.c.status == EffectStatus.RESERVED.value,
            ).order_by(
                production_effects.c.created_at,
                production_effects.c.effect_key,
            ).limit(limit)
        )).mappings().all()
    return [_decode(row) for row in rows]
