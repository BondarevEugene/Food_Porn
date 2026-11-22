"""Production release integrity: a manifest is never created for unreadable PDFs."""
import hashlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.private_pdf_store import pdf_object_key
from app.little_legend.release_orchestrator import (
    prepare_owned_release,
    send_owned_release,
)

OWNER = 123
STORY = 456
PDF = b"%PDF-1.4\n" + b"X" * 120
DIGEST = hashlib.sha256(PDF).hexdigest()


def _production():
    package = Mock()
    package.release.pdf_sha256 = DIGEST
    package.verified_pdf.return_value = PDF
    production = Mock()
    production.assemble.return_value = package
    return production, package


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "corrupt", "wrong_digest"])
async def test_bad_private_storage_never_creates_ready_manifest(failure):
    production, package = _production()
    store = Mock()
    if failure == "missing":
        store.get.side_effect = OSError("missing object")
    elif failure == "corrupt":
        store.get.return_value = b"not a PDF"
    else:
        store.get.return_value = b"%PDF-1.4\n" + b"Y" * 120
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
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            new_callable=AsyncMock,
        ) as register,
    ):
        with pytest.raises((OSError, ValueError, PermissionError)):
            await prepare_owned_release(
                owner_id=OWNER, story_id=STORY, art_store=Mock(), pdf_store=store,
            )
    register.assert_not_awaited()
    store.get.assert_called_once_with(
        key=pdf_object_key(owner_id=OWNER, story_id=STORY, pdf_sha256=DIGEST),
    )
    package.verified_pdf.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("registered", [False, True])
async def test_verified_private_pdf_registers_only_after_readback(registered):
    production, _package = _production()
    store = Mock()
    store.get.return_value = PDF
    manifest = Mock()
    events = []

    def persist(**kwargs):
        events.append("write")

    def readback(**kwargs):
        events.append("read")
        return PDF

    async def register(**kwargs):
        events.append("manifest")
        return manifest

    store.get.side_effect = readback
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
            side_effect=persist,
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release_pdf",
            new_callable=AsyncMock,
        ) as registered_write,
        patch(
            "app.little_legend.release_orchestrator.register_release",
            side_effect=register,
        ),
    ):
        if registered:
            async def tracked_registry(**kwargs):
                events.append("write")
            registered_write.side_effect = tracked_registry
        result = await prepare_owned_release(
            owner_id=OWNER, story_id=STORY, art_store=Mock(), pdf_store=store,
            registry_bucket="private" if registered else None,
        )
    assert result is manifest
    assert events == ["write", "read", "manifest"]


@pytest.mark.asyncio
async def test_missing_pdf_during_send_never_contacts_telegram():
    manifest = Mock(
        status=DeliveryStatus.READY,
        revision_fingerprint="a" * 64,
        pdf_sha256=DIGEST,
        scene_count=2,
    )
    sender = Mock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch(
            "app.little_legend.release_orchestrator.restore_release_pdf",
            side_effect=OSError("private PDF missing"),
        ),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock,
        ) as dispatch,
        patch(
            "app.little_legend.release_orchestrator.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
    ):
        with pytest.raises(OSError):
            await send_owned_release(
                owner_id=OWNER, story_id=STORY, pdf_store=Mock(), sender=sender,
            )
    dispatch.assert_not_awaited()
    mark.assert_not_awaited()
