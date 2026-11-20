"""Regression coverage for the production worker's crash-safe fences."""
from unittest.mock import AsyncMock

import pytest

from app.little_legend import paid_book_worker


@pytest.mark.asyncio
async def test_lost_lease_never_sends_pdf(monkeypatch):
    monkeypatch.setattr(
        paid_book_worker, "_resume_ready_delivery", AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        paid_book_worker, "_claim_one",
        AsyncMock(return_value={"quote_id": 12, "owner_id": 8, "lease": object()}),
    )
    monkeypatch.setattr(paid_book_worker, "_render", AsyncMock(return_value="private.pdf"))
    monkeypatch.setattr(paid_book_worker, "_mark_ready", AsyncMock(return_value=False))
    monkeypatch.setattr(paid_book_worker, "_keep_lease_alive", AsyncMock())
    delivery = AsyncMock()
    monkeypatch.setattr(paid_book_worker, "_deliver", delivery)
    assert await paid_book_worker.process_one() is True
    delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_pdf_commit_can_deliver_once(monkeypatch):
    monkeypatch.setattr(
        paid_book_worker, "_resume_ready_delivery", AsyncMock(return_value=False),
    )
    row = {"quote_id": 12, "owner_id": 8, "lease": object()}
    monkeypatch.setattr(paid_book_worker, "_claim_one", AsyncMock(return_value=row))
    monkeypatch.setattr(paid_book_worker, "_render", AsyncMock(return_value="private.pdf"))
    monkeypatch.setattr(paid_book_worker, "_mark_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(paid_book_worker, "_keep_lease_alive", AsyncMock())
    delivery = AsyncMock()
    monkeypatch.setattr(paid_book_worker, "_deliver", delivery)
    assert await paid_book_worker.process_one() is True
    delivery.assert_awaited_once_with(row, "private.pdf")


def test_fulfillment_model_matches_applied_delivery_and_lease_migrations():
    from app.little_legend.fulfillment_queue import fulfillment_jobs

    for name in (
        "asset_key", "delivery_started_at", "delivered_at",
        "lease_token", "lease_expires_at", "lease_attempts",
    ):
        assert name in fulfillment_jobs.c
