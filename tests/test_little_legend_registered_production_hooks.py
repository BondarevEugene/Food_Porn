"""Production hook guarantees: registration precedes successful release."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.release_orchestrator import prepare_owned_release


@pytest.mark.asyncio
async def test_release_registration_failure_does_not_create_manifest():
    package = Mock()
    package.release.pdf_sha256 = "a" * 64
    package.verified_pdf.return_value = b"%PDF-1.7\n" + b"x" * 120
    production = Mock()
    production.assemble.return_value = package
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
            "app.little_legend.release_orchestrator.register_release_pdf",
            new_callable=AsyncMock, side_effect=RuntimeError("Neon down"),
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            new_callable=AsyncMock,
        ) as manifest,
        pytest.raises(RuntimeError, match="Neon down"),
    ):
        await prepare_owned_release(
            owner_id=1, story_id=2, art_store=Mock(), pdf_store=Mock(),
            registry_bucket="private",
        )
    manifest.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_registration_precedes_manifest():
    package = Mock()
    package.release.pdf_sha256 = "a" * 64
    package.verified_pdf.return_value = b"%PDF-1.7\n" + b"x" * 120
    production = Mock()
    production.assemble.return_value = package
    events = []
    pdf = b"%PDF-1.7\\n" + b"x" * 120
    package.release.pdf_sha256 = __import__("hashlib").sha256(pdf).hexdigest()
    store = Mock()
    store.get.return_value = pdf

    async def registered(**kwargs):
        events.append("registered")

    async def manifest(**kwargs):
        events.append("manifest")
        return Mock()

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
            "app.little_legend.release_orchestrator.register_release_pdf",
            side_effect=registered,
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            side_effect=manifest,
        ),
    ):
        await prepare_owned_release(
            owner_id=1, story_id=2, art_store=Mock(), pdf_store=store,
            registry_bucket="private",
        )
    assert events == ["registered", "manifest"]
