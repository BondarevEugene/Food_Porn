"""Telegram PDF delivery is idempotent and never repeats ambiguous sends."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
)
from app.little_legend.telegram_book_delivery import (
    deliver_owned_book_once,
    delivery_effect_key,
)


def effect(status):
    return ProductionEffect(
        effect_key="ll_pdf_1_2_12345678901234567890123456789012",
        owner_id=1, story_id=2, kind=EffectKind.TELEGRAM_PDF,
        request_sha256="a" * 64, status=status,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_new_delivery_fences_before_sending(monkeypatch):
    import app.little_legend.telegram_book_delivery as delivery

    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(bot_token="test-token"))
    events = []

    async def reserve_effect(**kwargs):
        events.append("reserve")
        return effect(EffectStatus.RESERVED), True

    async def transition_effect(**kwargs):
        events.append(kwargs["next_status"].value)

    async def sender(**kwargs):
        events.append("send")
        assert kwargs["chat_id"] == 1
        return "456"

    monkeypatch.setattr(delivery, "reserve_effect", reserve_effect)
    monkeypatch.setattr(delivery, "transition_effect", transition_effect)
    result = await deliver_owned_book_once(
        owner_id=1, story_id=2, pdf=b"%PDF-1.4\nhello", sender=sender,
    )
    assert result["status"] == "confirmed"
    assert events == ["reserve", "dispatched", "send", "confirmed"]


@pytest.mark.asyncio
async def test_repeated_delivery_never_calls_telegram(monkeypatch):
    import app.little_legend.telegram_book_delivery as delivery

    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(bot_token="test-token"))

    async def reserve_effect(**kwargs):
        return effect(EffectStatus.UNCERTAIN), False

    async def sender(**kwargs):
        raise AssertionError("Repeated send")

    monkeypatch.setattr(delivery, "reserve_effect", reserve_effect)
    result = await deliver_owned_book_once(
        owner_id=1, story_id=2, pdf=b"%PDF-1.4\nhello", sender=sender,
    )
    assert result == {"status":"uncertain", "already_requested":True}


@pytest.mark.asyncio
async def test_failed_send_becomes_uncertain_without_retry(monkeypatch):
    import app.little_legend.telegram_book_delivery as delivery

    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(bot_token="test-token"))
    states = []

    async def reserve_effect(**kwargs):
        return effect(EffectStatus.RESERVED), True

    async def transition_effect(**kwargs):
        states.append(kwargs["next_status"])

    async def sender(**kwargs):
        raise TimeoutError("ambiguous Telegram outcome")

    monkeypatch.setattr(delivery, "reserve_effect", reserve_effect)
    monkeypatch.setattr(delivery, "transition_effect", transition_effect)
    with pytest.raises(TimeoutError):
        await deliver_owned_book_once(
            owner_id=1, story_id=2, pdf=b"%PDF-1.4\nhello", sender=sender,
        )
    assert states == [EffectStatus.DISPATCHED, EffectStatus.UNCERTAIN]


def test_delivery_key_is_stable_and_pdf_bound():
    a = delivery_effect_key(owner_id=1, story_id=2, pdf=b"%PDF-one")
    assert a == delivery_effect_key(owner_id=1, story_id=2, pdf=b"%PDF-one")
    assert a != delivery_effect_key(owner_id=1, story_id=2, pdf=b"%PDF-two")
    with pytest.raises(ValueError):
        delivery_effect_key(owner_id=1, story_id=2, pdf=b"not a PDF")
