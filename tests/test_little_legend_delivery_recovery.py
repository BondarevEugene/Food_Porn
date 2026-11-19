"""Worker must resume saved delivery before claiming more paid work."""
from unittest.mock import AsyncMock

import pytest

from app.little_legend import paid_book_worker


@pytest.mark.asyncio
async def test_ready_delivery_takes_priority_over_new_render(monkeypatch):
    resume = AsyncMock(return_value=True)
    claim = AsyncMock()
    monkeypatch.setattr(paid_book_worker, "_resume_ready_delivery", resume)
    monkeypatch.setattr(paid_book_worker, "_claim_one", claim)

    assert await paid_book_worker.process_one() is True
    resume.assert_awaited_once()
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_worker_does_not_generate_files(monkeypatch):
    monkeypatch.setattr(
        paid_book_worker, "_resume_ready_delivery", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(paid_book_worker, "_claim_one", AsyncMock(return_value=None))
    render = AsyncMock()
    monkeypatch.setattr(paid_book_worker, "_render", render)

    assert await paid_book_worker.process_one() is False
    render.assert_not_awaited()
