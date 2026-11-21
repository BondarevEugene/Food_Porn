"""R2 writes cannot report success until protected Neon registration commits."""
import hashlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.registered_artifact_writes import register_release_pdf


def valid_pdf():
    return b"%PDF-1.7\n" + b"x" * 120


@pytest.mark.asyncio
async def test_registered_release_commits_after_write():
    pdf = valid_pdf()
    store = Mock()
    session = AsyncMock()
    session.__aenter__.return_value = session
    with (
        patch(
            "app.little_legend.registered_artifact_writes.async_session_maker",
            return_value=session,
        ),
        patch(
            "app.little_legend.registered_artifact_writes.register",
            new_callable=AsyncMock,
            return_value=42,
        ) as register,
    ):
        result = await register_release_pdf(
            store=store, bucket="private", owner_id=1, story_id=2,
            pdf=pdf, pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        )
    store.put.assert_called_once()
    register.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert result.artifact_id == 42
    assert result.key.startswith("little-legend/releases/")


@pytest.mark.asyncio
async def test_neon_failure_never_deletes_customer_file_or_reports_success():
    pdf = valid_pdf()
    store = Mock()
    session = AsyncMock()
    session.__aenter__.return_value = session
    with (
        patch(
            "app.little_legend.registered_artifact_writes.async_session_maker",
            return_value=session,
        ),
        patch(
            "app.little_legend.registered_artifact_writes.register",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Neon unavailable"),
        ),
        pytest.raises(RuntimeError, match="Neon unavailable"),
    ):
        await register_release_pdf(
            store=store, bucket="private", owner_id=1, story_id=2,
            pdf=pdf, pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        )
    store.put.assert_called_once()
    store.delete.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_pdf_never_reaches_s3():
    store = Mock()
    with pytest.raises(ValueError):
        await register_release_pdf(
            store=store, bucket="private", owner_id=1, story_id=2,
            pdf=b"not a pdf", pdf_sha256="0" * 64,
        )
    store.put.assert_not_called()
