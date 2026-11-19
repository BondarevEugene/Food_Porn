"""Operator retention cycle must commit queueing before deletion."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.little_legend.vault_retention_cycle import run_private_retention_cycle


@pytest.mark.asyncio
async def test_retention_cycle_commits_before_physical_deletion():
    session = AsyncMock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=None)
    events = []

    async def queue(*args, **kwargs):
        events.append("queue")
        return ["asset-1", "asset-2"]

    async def commit():
        events.append("commit")

    async def erase(*args, **kwargs):
        events.append("erase")
        return {"deleted": 1, "failed": 1}

    session.commit.side_effect = commit
    with (
        patch(
            "app.little_legend.vault_retention_cycle.async_session_maker",
            return_value=manager,
        ),
        patch(
            "app.little_legend.vault_retention_cycle.request_expired_deletions",
            side_effect=queue,
        ),
        patch(
            "app.little_legend.vault_retention_cycle.erase_due_private_assets",
            side_effect=erase,
        ),
    ):
        report = await run_private_retention_cycle(
            deleter=Mock(), batch_size=10,
            now=datetime(2026, 11, 19, tzinfo=UTC),
        )
    assert events == ["queue", "commit", "erase"]
    assert report.expired_queued == 2
    assert report.physically_deleted == 1
    assert report.deletion_failed == 1
    assert not report.more_work_possible


@pytest.mark.asyncio
async def test_retention_cycle_rejects_bad_batch_without_database():
    with pytest.raises(ValueError, match="batch_size"):
        await run_private_retention_cycle(deleter=Mock(), batch_size=0)
    with pytest.raises(ValueError, match="batch_size"):
        await run_private_retention_cycle(deleter=Mock(), batch_size=101)
