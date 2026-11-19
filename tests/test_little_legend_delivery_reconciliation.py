"""Reconciliation never replays uncertain Telegram side effects."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import (
    RecoveryAction,
    diagnose_delivery,
    repair_confirmed_projection,
)
from app.little_legend.production_effect_ledger import EffectStatus


def fake_session(row):
    session = AsyncMock()
    result = Mock()
    result.mappings.return_value.one_or_none.return_value = row
    session.execute.return_value = result
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["dispatched", "uncertain"])
async def test_ambiguous_effect_requires_manual_review(status: str) -> None:
    manifest = Mock(pdf_sha256="a" * 64, status=DeliveryStatus.READY)
    row = {"status": status, "provider_reference": None}
    with (
        patch(
            "app.little_legend.delivery_reconciliation.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch(
            "app.little_legend.delivery_reconciliation.async_session_maker",
            fake_session(row),
        ),
        patch(
            "app.little_legend.delivery_reconciliation.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
    ):
        result = await repair_confirmed_projection(owner_id=42, story_id=12)
    assert result.action == RecoveryAction.MANUAL_REVIEW
    assert result.effect_status == EffectStatus(status)
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_effect_repairs_stale_manifest() -> None:
    ready = Mock(pdf_sha256="a" * 64, status=DeliveryStatus.READY)
    sent = Mock(
        pdf_sha256="a" * 64, status=DeliveryStatus.SENT,
        telegram_message_id=123,
    )
    row = {"status": "confirmed", "provider_reference": "123"}
    with (
        patch(
            "app.little_legend.delivery_reconciliation.get_release_manifest",
            new_callable=AsyncMock, side_effect=[ready, ready, sent],
        ),
        patch(
            "app.little_legend.delivery_reconciliation.async_session_maker",
            fake_session(row),
        ),
        patch(
            "app.little_legend.delivery_reconciliation.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
    ):
        result = await repair_confirmed_projection(owner_id=42, story_id=12)
    assert result.action == RecoveryAction.CONSISTENT
    mark.assert_awaited_once_with(
        owner_id=42, story_id=12, pdf_sha256="a" * 64,
        status=DeliveryStatus.SENT, message_id=123,
    )


@pytest.mark.asyncio
async def test_invalid_provider_acknowledgement_is_not_repaired() -> None:
    manifest = Mock(pdf_sha256="a" * 64, status=DeliveryStatus.READY)
    row = {"status": "confirmed", "provider_reference": "not-a-message-id"}
    with (
        patch(
            "app.little_legend.delivery_reconciliation.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch(
            "app.little_legend.delivery_reconciliation.async_session_maker",
            fake_session(row),
        ),
        patch(
            "app.little_legend.delivery_reconciliation.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
    ):
        result = await diagnose_delivery(owner_id=42, story_id=12)
    assert result.action == RecoveryAction.INCONSISTENT
    mark.assert_not_awaited()
