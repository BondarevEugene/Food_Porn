"""Orchestration tests: real-story loading, persistence and no-repeat delivery."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.release_orchestrator import (
    prepare_owned_release,
    send_owned_release,
)


@pytest.mark.asyncio
async def test_prepare_reuses_sealed_release_without_regenerating() -> None:
    manifest = Mock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch(
            "app.little_legend.release_orchestrator.load_owned_production",
            new_callable=AsyncMock,
        ) as load,
    ):
        result = await prepare_owned_release(
            owner_id=1, story_id=2, art_store=Mock(), pdf_store=Mock(),
        )
    assert result is manifest
    load.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_persists_before_registering_manifest() -> None:
    events = []
    production = Mock()
    package = Mock()
    production.assemble.return_value = package
    manifest = Mock()

    def persist(**kwargs):
        events.append("persist")

    async def register(**kwargs):
        events.append("register")
        return manifest

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
    ):
        result = await prepare_owned_release(
            owner_id=1, story_id=2, art_store=Mock(), pdf_store=Mock(),
        )
    assert result is manifest
    assert events == ["persist", "register"]
    load.assert_awaited_once_with(owner_id=1, story_id=2)


@pytest.mark.asyncio
async def test_send_rejects_missing_release_without_telegram() -> None:
    sender = Mock()
    with patch(
        "app.little_legend.release_orchestrator.get_release_manifest",
        new_callable=AsyncMock, return_value=None,
    ):
        with pytest.raises(PermissionError, match="not prepared"):
            await send_owned_release(
                owner_id=1, story_id=2, pdf_store=Mock(), sender=sender,
            )
    sender.send_pdf.assert_not_called()


@pytest.mark.asyncio
async def test_send_rejects_already_sent_without_telegram() -> None:
    sender = Mock()
    manifest = Mock(status=DeliveryStatus.SENT)
    with patch(
        "app.little_legend.release_orchestrator.get_release_manifest",
        new_callable=AsyncMock, return_value=manifest,
    ):
        with pytest.raises(PermissionError, match="already"):
            await send_owned_release(
                owner_id=1, story_id=2, pdf_store=Mock(), sender=sender,
            )
    sender.send_pdf.assert_not_called()


@pytest.mark.asyncio
async def test_send_projects_confirmed_effect_to_manifest() -> None:
    manifest = Mock(
        status=DeliveryStatus.READY,
        revision_fingerprint="a" * 64,
        pdf_sha256="b" * 64,
        scene_count=2,
    )
    delivery = Mock(status=DeliveryStatus.SENT, telegram_message_id=77)
    updated = Mock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch("app.little_legend.release_orchestrator.restore_release_pdf"),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock, return_value=delivery,
        ) as dispatch,
        patch(
            "app.little_legend.release_orchestrator.mark_release_delivery",
            new_callable=AsyncMock, return_value=updated,
        ) as mark,
    ):
        result = await send_owned_release(
            owner_id=1, story_id=2, pdf_store=Mock(), sender=Mock(),
        )
    assert result is updated
    dispatch.assert_awaited_once()
    mark.assert_awaited_once_with(
        owner_id=1, story_id=2, pdf_sha256="b" * 64,
        status=DeliveryStatus.SENT, message_id=77,
    )
