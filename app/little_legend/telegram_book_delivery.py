"""Owner-requested Telegram PDF delivery with durable idempotency fencing.

Never retry an ambiguous Telegram send automatically. A repeated request
returns the existing delivery state, not another message.
"""
from __future__ import annotations

import hashlib

import httpx

from app.config import get_settings
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    request_fingerprint,
    reserve_effect,
    transition_effect,
)


def delivery_effect_key(*, owner_id: int, story_id: int, pdf: bytes) -> str:
    if owner_id <= 0 or story_id <= 0 or not pdf.startswith(b"%PDF-"):
        raise ValueError("Valid owner, story and PDF are required")
    digest = hashlib.sha256(pdf).hexdigest()
    return f"ll_pdf_{owner_id}_{story_id}_{digest[:32]}"


async def send_telegram_pdf(
    *, token: str, chat_id: int, pdf: bytes, filename: str,
) -> str:
    """One Telegram Bot API call; only message ID is retained."""
    if not token or chat_id <= 0 or not pdf.startswith(b"%PDF-"):
        raise ValueError("Telegram delivery configuration or PDF is invalid")
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={"chat_id":str(chat_id), "disable_notification":"false"},
            files={"document":(filename, pdf, "application/pdf")},
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("ok") or not isinstance(payload.get("result"), dict):
        raise RuntimeError("Telegram did not acknowledge PDF delivery")
    message_id = payload["result"].get("message_id")
    if not isinstance(message_id, int) or message_id <= 0:
        raise RuntimeError("Telegram delivery acknowledgement is incomplete")
    return str(message_id)


async def deliver_owned_book_once(
    *, owner_id: int, story_id: int, pdf: bytes,
    sender=send_telegram_pdf,
) -> dict:
    """Dispatch only a newly reserved PDF; subsequent requests are read-only."""
    token = get_settings().bot_token
    if not token or token == "replace_me":
        raise RuntimeError("Telegram bot token is not configured")
    key = delivery_effect_key(owner_id=owner_id, story_id=story_id, pdf=pdf)
    digest = hashlib.sha256(pdf).hexdigest()
    effect, created = await reserve_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        kind=EffectKind.TELEGRAM_PDF,
        request_sha256=request_fingerprint({
            "owner_id":owner_id, "story_id":story_id, "pdf_sha256":digest,
        }),
    )
    if not created:
        return {"status":effect.status.value, "already_requested":True}
    # Commit irreversible dispatch marker before contacting Telegram.
    await transition_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        expected_status=EffectStatus.RESERVED,
        next_status=EffectStatus.DISPATCHED,
    )
    try:
        message_id = await sender(
            token=token, chat_id=owner_id, pdf=pdf,
            filename=f"little-legend-{story_id}.pdf",
        )
    except Exception:
        await transition_effect(
            effect_key=key, owner_id=owner_id, story_id=story_id,
            expected_status=EffectStatus.DISPATCHED,
            next_status=EffectStatus.UNCERTAIN,
        )
        raise
    await transition_effect(
        effect_key=key, owner_id=owner_id, story_id=story_id,
        expected_status=EffectStatus.DISPATCHED,
        next_status=EffectStatus.CONFIRMED,
        provider_reference=message_id,
    )
    return {"status":"confirmed", "already_requested":False}
