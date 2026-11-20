"""Paid Little Legend orders wait for editorial readiness, then auto-release."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.little_legend import paid_book_worker as worker


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, _statement):
        return Rows(self.pages.pop(0))

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_paid_unapproved_order_waits_without_claim(monkeypatch):
    row = {
        "quote_id": 1, "owner_id": 2, "story_id": 3,
        "created_at": datetime.now(UTC),
    }
    session = FakeSession([[row]])
    monkeypatch.setattr(worker, "async_session_maker", lambda: session)
    monkeypatch.setattr(
        worker, "has_verified_entitlement", AsyncMock(return_value=True),
    )
    monkeypatch.setattr(worker, "_release_ready", AsyncMock(return_value=False))
    claim = AsyncMock()
    monkeypatch.setattr(worker, "claim_pending", claim)

    assert await worker._claim_one() is None
    claim.assert_not_awaited()
    assert session.commits == 1


@pytest.mark.asyncio
async def test_ready_order_skips_unapproved_predecessor(monkeypatch):
    now = datetime.now(UTC)
    rows = [
        {"quote_id": 1, "owner_id": 2, "story_id": 3, "created_at": now},
        {"quote_id": 4, "owner_id": 2, "story_id": 5, "created_at": now},
    ]
    session = FakeSession([rows])
    monkeypatch.setattr(worker, "async_session_maker", lambda: session)
    monkeypatch.setattr(
        worker, "has_verified_entitlement", AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        worker, "_release_ready", AsyncMock(side_effect=[False, True]),
    )
    lease = SimpleNamespace(token="token")
    claim = AsyncMock(return_value=lease)
    monkeypatch.setattr(worker, "claim_pending", claim)

    result = await worker._claim_one()
    assert result["quote_id"] == 4
    assert result["lease"] is lease
    assert claim.await_count == 1
    assert claim.await_args.kwargs["quote_id"] == 4
    assert session.commits == 1


@pytest.mark.asyncio
async def test_pending_scan_continues_after_full_page(monkeypatch):
    now = datetime.now(UTC)
    first = [
        {"quote_id": i, "owner_id": 2, "story_id": i, "created_at": now}
        for i in range(1, 26)
    ]
    last = {"quote_id": 26, "owner_id": 2, "story_id": 26, "created_at": now}
    session = FakeSession([first, [last]])
    monkeypatch.setattr(worker, "async_session_maker", lambda: session)
    monkeypatch.setattr(
        worker, "has_verified_entitlement", AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        worker, "_release_ready", AsyncMock(side_effect=[False] * 25 + [True]),
    )
    monkeypatch.setattr(
        worker, "claim_pending", AsyncMock(return_value=SimpleNamespace(token="t")),
    )
    assert (await worker._claim_one())["quote_id"] == 26
    assert session.commits == 2
