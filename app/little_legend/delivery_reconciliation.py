"""Read-only recovery diagnosis for Little Legend PDF deliveries.

Never call Telegram, retry a delivery or turn an ambiguous effect into a
confirmed one. A confirmed provider reference may repair a stale projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    production_effects,
)
from app.little_legend.release_manifest_store import (
    get_release_manifest,
    mark_release_delivery,
)
from app.little_legend.telegram_pdf_dispatch import pdf_delivery_effect_key


class RecoveryAction(StrEnum):
    NO_EFFECT = "no_effect"
    IN_FLIGHT = "in_flight"
    MANUAL_REVIEW = "manual_review"
    REPAIR_PROJECTION = "repair_projection"
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"


@dataclass(frozen=True)
class DeliveryDiagnosis:
    owner_id: int
    story_id: int
    action: RecoveryAction
    effect_status: EffectStatus | None
    manifest_status: DeliveryStatus | None
    telegram_message_id: int | None = None


async def diagnose_delivery(*, owner_id: int, story_id: int) -> DeliveryDiagnosis:
    """Owner-scoped diagnosis; no external provider requests."""
    if owner_id <= 0 or story_id <= 0:
        raise PermissionError("Invalid delivery identity")
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None:
        raise PermissionError("Release not found")
    key = pdf_delivery_effect_key(
        owner_id=owner_id, story_id=story_id, pdf_sha256=manifest.pdf_sha256,
    )
    async with async_session_maker() as session:
        row = (await session.execute(select(production_effects).where(
            production_effects.c.effect_key == key,
            production_effects.c.owner_id == owner_id,
            production_effects.c.story_id == story_id,
            production_effects.c.kind == EffectKind.TELEGRAM_PDF.value,
        ))).mappings().one_or_none()
    status = EffectStatus(row["status"]) if row else None
    message_id = None
    if status == EffectStatus.CONFIRMED:
        reference = row["provider_reference"]
        if reference and reference.isascii() and reference.isdecimal():
            message_id = int(reference)
        if not message_id or message_id <= 0:
            return DeliveryDiagnosis(
                owner_id, story_id, RecoveryAction.INCONSISTENT,
                status, manifest.status,
            )
        if manifest.status == DeliveryStatus.SENT:
            action = (
                RecoveryAction.CONSISTENT
                if manifest.telegram_message_id == message_id
                else RecoveryAction.INCONSISTENT
            )
        else:
            action = RecoveryAction.REPAIR_PROJECTION
    elif status in {EffectStatus.DISPATCHED, EffectStatus.UNCERTAIN}:
        action = RecoveryAction.MANUAL_REVIEW
    elif status == EffectStatus.RESERVED:
        action = RecoveryAction.IN_FLIGHT
    elif manifest.status == DeliveryStatus.READY:
        action = RecoveryAction.NO_EFFECT
    else:
        action = RecoveryAction.INCONSISTENT
    return DeliveryDiagnosis(
        owner_id, story_id, action, status, manifest.status, message_id,
    )


async def repair_confirmed_projection(
    *, owner_id: int, story_id: int,
) -> DeliveryDiagnosis:
    """Mirror a *confirmed* ledger acknowledgement; never initiate a send."""
    diagnosis = await diagnose_delivery(owner_id=owner_id, story_id=story_id)
    if diagnosis.action != RecoveryAction.REPAIR_PROJECTION:
        return diagnosis
    if diagnosis.telegram_message_id is None:
        raise PermissionError("Provider confirmation required")
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None:
        raise PermissionError("Release not found")
    await mark_release_delivery(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=manifest.pdf_sha256, status=DeliveryStatus.SENT,
        message_id=diagnosis.telegram_message_id,
    )
    return await diagnose_delivery(owner_id=owner_id, story_id=story_id)
