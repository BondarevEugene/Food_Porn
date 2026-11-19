"""Owner-scoped Telegram PDF dispatch with a durable, no-retry effect fence.

The caller must supply a verified release package from trusted private
storage. No external call is made until the DISPATCHED marker is committed.
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from app.little_legend.book_delivery import BookDelivery, begin_delivery, confirm_delivery, mark_uncertain
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    request_fingerprint,
    reserve_effect,
    transition_effect,
)
from app.little_legend.release_package import ReleasePackage


class PDFSender(Protocol):
    async def send_pdf(self, *, chat_id: int, pdf: bytes, filename: str) -> int: ...


def pdf_delivery_effect_key(*, owner_id: int, story_id: int, pdf_sha256: str) -> str:
    if owner_id <= 0 or story_id <= 0 or len(pdf_sha256) != 64:
        raise ValueError("Invalid PDF delivery identity")
    digest = hashlib.sha256(
        f"{owner_id}:{story_id}:{pdf_sha256}".encode("ascii")
    ).hexdigest()
    return f"llpdf:{digest}"


async def dispatch_release_pdf(
    *, package: ReleasePackage, owner_id: int, story_id: int,
    sender: PDFSender,
) -> BookDelivery:
    """Attempt exactly one send for a sealed PDF; ambiguous sends stay fenced.

    A repeated call for the same release is rejected even if Telegram did not
    acknowledge the first attempt. Operator reconciliation is required.
    """
    pdf = package.verified_pdf(owner_id=owner_id, story_id=story_id)
    if package.delivery.status.value != "ready":
        raise PermissionError("Only a ready delivery can be dispatched")
    key = pdf_delivery_effect_key(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=package.release.pdf_sha256,
    )
    fingerprint = request_fingerprint({
        "owner_id": owner_id, "story_id": story_id,
        "pdf_sha256": package.release.pdf_sha256,
        "destination": owner_id,
    })
    effect, created = await reserve_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        kind=EffectKind.TELEGRAM_PDF, request_sha256=fingerprint,
    )
    if not created or effect.status != EffectStatus.RESERVED:
        raise PermissionError("PDF delivery was already reserved or dispatched")
    await transition_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        expected_status=EffectStatus.RESERVED,
        next_status=EffectStatus.DISPATCHED,
    )
    attempt = begin_delivery(package.delivery, attempt_id=key)
    try:
        message_id = await sender.send_pdf(
            chat_id=owner_id, pdf=pdf,
            filename=f"little-legend-{story_id}.pdf",
        )
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise ValueError("Telegram did not return a valid message ID")
    except Exception:
        await transition_effect(
            effect_key=key, owner_id=owner_id, story_id=story_id,
            expected_status=EffectStatus.DISPATCHED,
            next_status=EffectStatus.UNCERTAIN,
        )
        return mark_uncertain(attempt, attempt_id=key)
    await transition_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        expected_status=EffectStatus.DISPATCHED,
        next_status=EffectStatus.CONFIRMED,
        provider_reference=str(message_id),
    )
    return confirm_delivery(attempt, attempt_id=key, message_id=message_id)
