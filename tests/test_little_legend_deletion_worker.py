"""Object deletion worker safety contracts."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.little_legend.deletion_worker import delete_pending_assets


class Store:
    def __init__(self, fail=False):
        self.deleted = []
        self.fail = fail

    def delete(self, *, key):
        self.deleted.append(key)
        if self.fail:
            raise RuntimeError("private provider message")

    def put(self, *, key, data, content_type):
        raise AssertionError("not used")


def _session(rows):
    session = MagicMock()
    session.execute = AsyncMock()
    session.execute.side_effect = [
        MagicMock(all=lambda: rows),
        *[MagicMock() for _ in rows],
    ]
    return session


@pytest.mark.asyncio
async def test_success_only_after_object_delete():
    key = "little-legend/private/" + "a" * 48
    session = _session([("asset1", key, 0)])
    store = Store()
    result = await delete_pending_assets(session, store)
    assert result == {"selected": 1, "deleted": 1, "failed": 0}
    assert store.deleted == [key]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_failure_is_retryable_and_no_sensitive_exception_leaks():
    key = "little-legend/private/" + "b" * 48
    session = _session([("asset2", key, 2)])
    store = Store(fail=True)
    errors = []
    result = await delete_pending_assets(session, store, on_error=errors.append)
    assert result == {"selected": 1, "deleted": 0, "failed": 1}
    assert errors == ["OBJECT_DELETE_FAILED"]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_invalid_key_never_reaches_object_store():
    session = _session([("asset3", "../other", 0)])
    store = Store()
    result = await delete_pending_assets(session, store)
    assert result["failed"] == 1
    assert store.deleted == []


@pytest.mark.asyncio
async def test_empty_batch():
    assert await delete_pending_assets(_session([]), Store()) == {
        "selected": 0, "deleted": 0, "failed": 0,
    }


@pytest.mark.asyncio
async def test_invalid_batch():
    with pytest.raises(ValueError):
        await delete_pending_assets(_session([]), Store(), batch_size=0)


@pytest.mark.asyncio
async def test_naive_time_rejected():
    with pytest.raises(ValueError):
        await delete_pending_assets(
            _session([]), Store(), now=datetime(2026, 1, 1),
        )
