"""Retention run history must never store private fields."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.little_legend.retention_history import (
    recent_retention_runs,
    record_retention_run,
    safe_snapshot,
)


def result():
    return {
        "audit": {
            "expired_not_deleted": 2,
            "pending_over_24h": 1,
            "exhausted_retries": 0,
            "child_name": "PRIVATE_CHILD",
            "object_key": "PRIVATE_KEY",
        },
        "operations": {
            "status": "warning",
            "codes": ["RETENTION_EXPIRED_BACKLOG"],
            "free_text": "PRIVATE_CHILD",
        },
        "notification": {"sent": False},
        "retention": {"physically_deleted": 3, "deletion_failed": 0},
    }


def test_snapshot_only_approved_fields():
    snapshot = safe_snapshot(result())
    assert snapshot["mode"] == "execute"
    assert snapshot["physically_deleted"] == 3
    assert snapshot["expired_not_deleted"] == 2
    assert "PRIVATE_CHILD" not in repr(snapshot)
    assert "PRIVATE_KEY" not in repr(snapshot)


def test_reject_unknown_code():
    payload = result()
    payload["operations"]["codes"] = ["PRIVATE_KEY"]
    with pytest.raises(ValueError, match="codes"):
        safe_snapshot(payload)


@pytest.mark.parametrize("bad", [-1, True, "2", None])
def test_reject_bad_count(bad):
    payload = result()
    payload["audit"]["expired_not_deleted"] = bad
    with pytest.raises(ValueError, match="count"):
        safe_snapshot(payload)


def test_dry_run_mode():
    payload = result()
    del payload["retention"]
    assert safe_snapshot(payload)["mode"] == "dry-run"


@pytest.mark.asyncio
async def test_record_commits_once():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await record_retention_run(session, result())
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_limit_is_bounded():
    session = MagicMock()
    session.execute = AsyncMock()
    with pytest.raises(ValueError, match="limit"):
        await recent_retention_runs(session, limit=101)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_serializes_time():
    session = MagicMock()
    row = {
        "id": 1, "checked_at": datetime(2026, 11, 20),
        "status": "ok", "codes": [],
    }
    response = MagicMock()
    response.mappings.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=response)
    rows = await recent_retention_runs(session)
    assert rows[0]["checked_at"] == "2026-11-20T00:00:00"
