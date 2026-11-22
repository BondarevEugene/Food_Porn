"""Production-to-delivery contract: sealed bytes, ownership and no AI on send."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.release_orchestrator import (
    prepare_owned_release,
    send_owned_release,
)


@pytest.mark.asyncio
async def test_approved_production_is_persisted_before_manifest_registration() -> None:
    """Preparation must never publish a manifest before the PDF is durable."""
    events = []
    production = Mock()
    package = Mock()
    production.assemble.return_value = package
    expected = Mock()
    package.release.pdf_sha256 = "a" * 64

    def persist(**kwargs):
        assert kwargs["package"] is package
        assert kwargs["owner_id"] == 42
        assert kwargs["story_id"] == 12
        events.append("private_pdf_persisted")

    async def register(**kwargs):
        assert kwargs["package"] is package
        events.append("manifest_registered")
        return expected

    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "app.little_legend.release_orchestrator.load_owned_production",
            new_callable=AsyncMock, return_value=production,
        ) as load,
        patch(
            "app.little_legend.release_orchestrator.persist_release_pdf",
            side_effect=persist,
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            side_effect=register,
        ),
        patch("app.little_legend.release_orchestrator.validate_pdf"),
    ):
        result = await prepare_owned_release(
            owner_id=42, story_id=12, art_store=Mock(), pdf_store=Mock(),
        )
    assert result is expected
    assert events == ["private_pdf_persisted", "manifest_registered"]
    load.assert_awaited_once_with(owner_id=42, story_id=12)
    production.assemble.assert_called_once()


@pytest.mark.asyncio
async def test_failed_private_storage_never_registers_release() -> None:
    production = Mock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "app.little_legend.release_orchestrator.load_owned_production",
            new_callable=AsyncMock, return_value=production,
        ),
        patch(
            "app.little_legend.release_orchestrator.persist_release_pdf",
            side_effect=OSError("private storage unavailable"),
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            new_callable=AsyncMock,
        ) as register,
    ):
        with pytest.raises(OSError, match="unavailable"):
            await prepare_owned_release(
                owner_id=42, story_id=12, art_store=Mock(), pdf_store=Mock(),
            )
    register.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_sealed_pdf_never_reserves_or_sends() -> None:
    sealed = Mock(
        status=DeliveryStatus.READY, revision_fingerprint="b" * 64,
        pdf_sha256="a" * 64, scene_count=2,
    )
    sender = AsyncMock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=sealed,
        ),
        patch(
            "app.little_legend.release_orchestrator.restore_release_pdf",
            side_effect=FileNotFoundError("sealed PDF missing"),
        ),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock,
        ) as dispatch,
    ):
        with pytest.raises(FileNotFoundError):
            await send_owned_release(
                owner_id=42, story_id=12, pdf_store=Mock(), sender=sender,
            )
    dispatch.assert_not_awaited()
    sender.send_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_only_uses_sealed_pdf_without_reassembly() -> None:
    sealed = Mock(
        status=DeliveryStatus.READY, revision_fingerprint="b" * 64,
        pdf_sha256="a" * 64, scene_count=2,
    )
    package = Mock()
    outcome = Mock(status=DeliveryStatus.SENT, telegram_message_id=91)
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=sealed,
        ),
        patch(
            "app.little_legend.release_orchestrator.restore_release_pdf",
            return_value=package,
        ) as restore,
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock, return_value=outcome,
        ) as dispatch,
        patch(
            "app.little_legend.release_orchestrator.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
        patch(
            "app.little_legend.release_orchestrator.load_owned_production",
            new_callable=AsyncMock,
        ) as load,
    ):
        await send_owned_release(
            owner_id=42, story_id=12, pdf_store=Mock(), sender=AsyncMock(),
        )
    restore.assert_called_once()
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["package"] is package
    mark.assert_awaited_once_with(
        owner_id=42, story_id=12, pdf_sha256="a" * 64,
        status=DeliveryStatus.SENT, message_id=91,
    )
    load.assert_not_awaited()
