"""Recover a release projection from the durable Telegram effect without sending."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.production_effect_ledger import EffectStatus
from app.little_legend.release_orchestrator import reconcile_owned_delivery


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reference", "expected"),
    [
        (EffectStatus.CONFIRMED, "917", DeliveryStatus.SENT),
        (EffectStatus.UNCERTAIN, None, DeliveryStatus.UNCERTAIN),
    ],
)
async def test_reconcile_terminal_effect(status, reference, expected):
    manifest = Mock(status=DeliveryStatus.READY, pdf_sha256="a" * 64)
    effect = Mock(status=status, provider_reference=reference)
    with (
        patch("app.little_legend.release_orchestrator.get_release_manifest",
              new_callable=AsyncMock, return_value=manifest),
        patch("app.little_legend.release_orchestrator.get_effect",
              new_callable=AsyncMock, return_value=effect) as lookup,
        patch("app.little_legend.release_orchestrator.mark_release_delivery",
              new_callable=AsyncMock) as mark,
    ):
        await reconcile_owned_delivery(owner_id=42, story_id=12)
    assert lookup.await_args.kwargs["owner_id"] == 42
    assert lookup.await_args.kwargs["story_id"] == 12
    assert mark.await_args.kwargs["status"] == expected
    if expected == DeliveryStatus.SENT:
        assert mark.await_args.kwargs["message_id"] == 917
    else:
        assert "message_id" not in mark.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [EffectStatus.RESERVED, EffectStatus.DISPATCHED])
async def test_inflight_effect_is_not_projected(status):
    manifest = Mock(status=DeliveryStatus.READY, pdf_sha256="a" * 64)
    with (
        patch("app.little_legend.release_orchestrator.get_release_manifest",
              new_callable=AsyncMock, return_value=manifest),
        patch("app.little_legend.release_orchestrator.get_effect",
              new_callable=AsyncMock,
              return_value=Mock(status=status, provider_reference=None)),
        patch("app.little_legend.release_orchestrator.mark_release_delivery",
              new_callable=AsyncMock) as mark,
    ):
        assert await reconcile_owned_delivery(owner_id=42, story_id=12) is manifest
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_acknowledgement_does_not_claim_sent():
    manifest = Mock(status=DeliveryStatus.READY, pdf_sha256="a" * 64)
    with (
        patch("app.little_legend.release_orchestrator.get_release_manifest",
              new_callable=AsyncMock, return_value=manifest),
        patch("app.little_legend.release_orchestrator.get_effect",
              new_callable=AsyncMock,
              return_value=Mock(status=EffectStatus.CONFIRMED,
                                provider_reference="bad")),
        patch("app.little_legend.release_orchestrator.mark_release_delivery",
              new_callable=AsyncMock) as mark,
    ):
        with pytest.raises(ValueError, match="message ID"):
            await reconcile_owned_delivery(owner_id=42, story_id=12)
    mark.assert_not_awaited()
