"""Auto delivery: explicit opt-in, pending book, confirmed send, uncertain send."""
from datetime import UTC, datetime

import pytest

from app.little_legend.auto_delivery_worker import (
    auto_delivery_key,
    opt_in_auto_delivery,
    process_auto_delivery_once,
)
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
)


def _effect(status=EffectStatus.RESERVED):
    return ProductionEffect(
        effect_key=auto_delivery_key(owner_id=1, story_id=2),
        owner_id=1, story_id=2,
        kind=EffectKind.TELEGRAM_AUTO_REQUEST,
        request_sha256="a" * 64,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_opt_in_is_owner_scoped_and_idempotent(monkeypatch):
    import app.little_legend.auto_delivery_worker as worker

    calls = []

    async def reserve(**kwargs):
        calls.append(kwargs)
        return _effect(), len(calls) == 1

    monkeypatch.setattr(worker, "reserve_effect", reserve)
    assert (await opt_in_auto_delivery(owner_id=1, story_id=2))["created"]
    assert not (await opt_in_auto_delivery(owner_id=1, story_id=2))["created"]
    assert all(call["kind"] == EffectKind.TELEGRAM_AUTO_REQUEST for call in calls)
    assert all(call["owner_id"] == 1 for call in calls)


@pytest.mark.asyncio
async def test_unfinished_book_remains_pending():
    events = []

    async def pending(**kwargs):
        return [_effect()]

    async def load_pdf(**kwargs):
        events.append("not_ready")
        return None

    async def deliver(**kwargs):
        raise AssertionError("Never send unfinished PDF")

    assert not await process_auto_delivery_once(
        pending=pending, load_pdf=load_pdf, deliver=deliver,
    )
    assert events == ["not_ready"]


@pytest.mark.asyncio
async def test_ready_book_is_sent_once_and_confirmed(monkeypatch):
    import app.little_legend.auto_delivery_worker as worker

    transitions = []

    async def pending(**kwargs):
        return [_effect()]

    async def load_pdf(**kwargs):
        return b"%PDF-1.4\nready"

    async def deliver(**kwargs):
        return {"status":"confirmed", "already_requested":False}

    async def transition(**kwargs):
        transitions.append(kwargs["next_status"])

    monkeypatch.setattr(worker, "transition_effect", transition)
    assert await process_auto_delivery_once(
        pending=pending, load_pdf=load_pdf, deliver=deliver,
    )
    assert transitions == [EffectStatus.DISPATCHED, EffectStatus.CONFIRMED]


@pytest.mark.asyncio
async def test_ambiguous_telegram_result_never_retries(monkeypatch):
    import app.little_legend.auto_delivery_worker as worker

    transitions = []
    sends = []

    async def pending(**kwargs):
        return [_effect()]

    async def load_pdf(**kwargs):
        return b"%PDF-1.4\nready"

    async def deliver(**kwargs):
        sends.append(1)
        return {"status":"uncertain", "already_requested":True}

    async def transition(**kwargs):
        transitions.append(kwargs["next_status"])

    monkeypatch.setattr(worker, "transition_effect", transition)
    assert await process_auto_delivery_once(
        pending=pending, load_pdf=load_pdf, deliver=deliver,
    )
    assert sends == [1]
    assert transitions == [EffectStatus.DISPATCHED, EffectStatus.UNCERTAIN]


def test_auto_key_rejects_invalid_owner():
    with pytest.raises(ValueError):
        auto_delivery_key(owner_id=0, story_id=2)
