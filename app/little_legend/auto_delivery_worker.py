"""Opt-in, durable premium book delivery after production completes.

The opt-in lives in the existing Neon effect ledger. The PDF effect ledger
independently fences Telegram sendDocument, so two workers cannot send twice.
A crashed worker can resume pending opt-ins without reissuing an ambiguous send.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException

from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
    list_pending_auto_delivery,
    request_fingerprint,
    reserve_effect,
    transition_effect,
)
from app.little_legend.telegram_book_delivery import deliver_owned_book_once

logger = logging.getLogger(__name__)


def auto_delivery_key(*, owner_id: int, story_id: int) -> str:
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid story owner")
    return f"ll_auto_pdf_{owner_id}_{story_id}"


async def opt_in_auto_delivery(*, owner_id: int, story_id: int) -> dict:
    """Owner-scoped request. Does not send anything until the book is ready."""
    effect, created = await reserve_effect(
        effect_key=auto_delivery_key(owner_id=owner_id, story_id=story_id),
        owner_id=owner_id, story_id=story_id,
        kind=EffectKind.TELEGRAM_AUTO_REQUEST,
        request_sha256=request_fingerprint({
            "owner_id":owner_id, "story_id":story_id, "edition":"premium",
        }),
    )
    return {"status":effect.status.value, "created":created}


async def get_auto_delivery_status(*, owner_id: int, story_id: int) -> dict:
    """Owner-only status; never expose Telegram message IDs or tokens."""
    from sqlalchemy import select

    from app.database.session import async_session_maker
    from app.little_legend.production_effect_ledger import production_effects
    from app.little_legend.router import stories

    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
        if owned is None:
            raise PermissionError("Story does not belong to owner")
        status = (await session.execute(select(production_effects.c.status).where(
            production_effects.c.effect_key == auto_delivery_key(
                owner_id=owner_id, story_id=story_id,
            ),
            production_effects.c.owner_id == owner_id,
            production_effects.c.story_id == story_id,
            production_effects.c.kind == EffectKind.TELEGRAM_AUTO_REQUEST.value,
        ))).scalar_one_or_none()
    return {"status":status or "not_requested"}


async def render_ready_premium_pdf(*, owner_id: int, story_id: int) -> bytes | None:
    """Reuse all owner, manuscript, illustration and private-storage checks."""
    from app.little_legend.router import download_premium_illustrated_book

    try:
        response = await download_premium_illustrated_book(story_id, owner_id)
    except HTTPException as exc:
        if exc.status_code == 409:
            return None
        raise
    return response.body


async def _mark_auto_delivery(
    effect: ProductionEffect, *, status: EffectStatus,
) -> None:
    await transition_effect(
        effect_key=effect.effect_key,
        owner_id=effect.owner_id,
        story_id=effect.story_id,
        expected_status=EffectStatus.RESERVED,
        next_status=EffectStatus.DISPATCHED,
    )
    await transition_effect(
        effect_key=effect.effect_key,
        owner_id=effect.owner_id,
        story_id=effect.story_id,
        expected_status=EffectStatus.DISPATCHED,
        next_status=(
            EffectStatus.CONFIRMED if status == EffectStatus.CONFIRMED
            else EffectStatus.UNCERTAIN
        ),
        provider_reference="telegram_pdf_confirmed"
        if status == EffectStatus.CONFIRMED else None,
    )


async def process_auto_delivery_once(
    *, load_pdf=render_ready_premium_pdf,
    deliver=deliver_owned_book_once,
    pending=list_pending_auto_delivery,
) -> bool:
    """Check one pending opt-in; return False when no eligible work exists.

    A not-yet-ready book remains pending. Ambiguous sends never auto-retry.
    """
    requests = await pending(limit=20)
    if not requests:
        return False
    for effect in requests:
        try:
            pdf = await load_pdf(
                owner_id=effect.owner_id, story_id=effect.story_id,
            )
            if pdf is None:
                continue
            result = await deliver(
                owner_id=effect.owner_id, story_id=effect.story_id, pdf=pdf,
            )
            status = EffectStatus(result["status"])
            if status in {EffectStatus.CONFIRMED, EffectStatus.UNCERTAIN}:
                await _mark_auto_delivery(effect, status=status)
            elif status == EffectStatus.DISPATCHED:
                # Worker may have crashed after Telegram accepted the message.
                # Never retry an ambiguous dispatch.
                await _mark_auto_delivery(effect, status=EffectStatus.UNCERTAIN)
            return True
        except asyncio.CancelledError:
            raise
        except PermissionError:
            logger.warning("Little Legend auto-delivery authorization revoked")
        except Exception:
            # A durable PDF dispatch fence prevents duplicate Telegram sends.
            logger.exception("Little Legend auto-delivery needs reconciliation")
    return False


async def run_auto_delivery_loop(*, poll_seconds: float = 15.0) -> None:
    """Run as a dedicated Railway worker; never on every web process."""
    if poll_seconds < 1:
        raise ValueError("Poll interval must be at least one second")
    while True:
        try:
            await process_auto_delivery_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Little Legend auto-delivery polling failed")
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_auto_delivery_loop())
