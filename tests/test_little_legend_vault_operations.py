"""Retention orchestration contracts."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.little_legend.vault_operations import (
    queue_story_deletion,
    requeue_failed_deletions,
    retention_health,
    run_retention_cycle,
)


@pytest.mark.asyncio
async def test_retry_requires_due_timestamp_and_cooldown():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=2))
    assert await requeue_failed_deletions(session) == 2
    session.execute.assert_awaited_once()
    with pytest.raises(ValueError):
        await requeue_failed_deletions(session, retry_after=timedelta(seconds=1))


@pytest.mark.asyncio
async def test_health_is_aggregate_only():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(
        one=lambda: (3, datetime(2026, 1, 1, tzinfo=UTC))
    ))
    result = await retention_health(
        session, now=datetime(2026, 1, 2, tzinfo=UTC)
    )
    assert result == {"pending": 3, "oldest_pending_seconds": 86400}


@pytest.mark.asyncio
async def test_owner_scope_required_for_erasure():
    session = MagicMock()
    with pytest.raises(ValueError):
        await queue_story_deletion(session, owner_id=0, story_id=1)


@pytest.mark.asyncio
async def test_cycle_commits_between_queue_and_delete():
    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        def __init__(self):
            self.transaction = Transaction()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self.transaction

    with (
        patch(
            "app.little_legend.vault_operations.requeue_failed_deletions",
            new_callable=AsyncMock, return_value=2,
        ),
        patch(
            "app.little_legend.vault_operations.request_expired_deletions",
            new_callable=AsyncMock, return_value=["a"],
        ) as queue,
        patch(
            "app.little_legend.vault_operations.delete_pending_assets",
            new_callable=AsyncMock,
            return_value={"deleted": 1, "failed": 0},
        ) as delete,
        patch(
            "app.little_legend.vault_operations.retention_health",
            new_callable=AsyncMock,
            return_value={"pending": 0, "oldest_pending_seconds": None},
        ),
    ):
        report = await run_retention_cycle(Session, MagicMock())
        assert report.queued == 1
        assert report.retried == 2
        assert report.deleted == 1
        queue.assert_awaited_once()
        delete.assert_awaited_once()
