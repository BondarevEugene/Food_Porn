"""Crash-window regressions: a Telegram PDF is never blindly replayed."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import (
    RecoveryAction,
    diagnose_delivery,
)
from app.little_legend.production_effect_ledger import EffectStatus
from app.little_legend.release_orchestrator import send_owned_release


def manifest(status: DeliveryStatus = DeliveryStatus.READY) -> Mock:
    return Mock(
        status=status, pdf_sha256="a" * 64,
        revision_fingerprint="b" * 64, scene_count=2,
        telegram_message_id=None,
    )


@pytest.mark.asyncio
async def test_telegram_acknowledged_but_projection_write_failed() -> None:
    """A persisted confirmation survives a failed manifest projection."""
    sender = AsyncMock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest(),
        ),
        patch("app.little_legend.release_orchestrator.restore_release_pdf"),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock,
            return_value=Mock(
                status=DeliveryStatus.SENT, telegram_message_id=71,
            ),
        ) as dispatch,
        patch(
            "app.little_legend.release_orchestrator.mark_release_delivery",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Neon unavailable after Telegram ACK"),
        ),
    ):
        with pytest.raises(ConnectionError):
            await send_owned_release(
                owner_id=42, story_id=12, pdf_store=Mock(), sender=sender,
            )
    dispatch.assert_awaited_once()
    sender.send_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_uncertain_manifest_never_replays_telegram() -> None:
    sender = AsyncMock()
    with patch(
        "app.little_legend.release_orchestrator.get_release_manifest",
        new_callable=AsyncMock,
        return_value=manifest(DeliveryStatus.UNCERTAIN),
    ):
        with pytest.raises(PermissionError, match="already"):
            await send_owned_release(
                owner_id=42, story_id=12, pdf_store=Mock(), sender=sender,
            )
    sender.send_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_manifest_after_crash_still_has_ledger_fence() -> None:
    """If a worker dies before projection, durable effect must block replay."""
    sender = AsyncMock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest(),
        ),
        patch("app.little_legend.release_orchestrator.restore_release_pdf"),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock,
            side_effect=PermissionError("PDF delivery was already reserved"),
        ) as dispatch,
    ):
        with pytest.raises(PermissionError, match="already reserved"):
            await send_owned_release(
                owner_id=42, story_id=12, pdf_store=Mock(), sender=sender,
            )
    dispatch.assert_awaited_once()
    sender.send_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_does_not_treat_dispatched_as_confirmed() -> None:
    """A crash after the dispatch fence requires operator review."""
    session = AsyncMock()
    rows = Mock()
    rows.mappings.return_value.one_or_none.return_value = {
        "status": EffectStatus.DISPATCHED.value,
        "provider_reference": None,
    }
    session.execute.return_value = rows
    factory = Mock()
    factory.return_value = AsyncMock()
    factory.return_value.__aenter__.return_value = session
    with (
        patch(
            "app.little_legend.delivery_reconciliation.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest(),
        ),
        patch(
            "app.little_legend.delivery_reconciliation.async_session_maker",
            factory,
        ),
    ):
        diagnosis = await diagnose_delivery(owner_id=42, story_id=12)
    assert diagnosis.action == RecoveryAction.MANUAL_REVIEW
    assert diagnosis.telegram_message_id is None
