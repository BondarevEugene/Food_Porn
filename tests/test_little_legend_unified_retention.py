"""Canonical retention worker contract and legacy adapter."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.little_legend.vault_operations import run_retention_cycle


@pytest.mark.asyncio
async def test_legacy_cycle_delegates_to_one_canonical_worker():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=transaction)
    transaction.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = transaction
    factory = Mock(return_value=session)
    store = Mock()
    instant = datetime(2026, 11, 19, tzinfo=UTC)
    with (
        patch(
            "app.little_legend.vault_operations.request_expired_deletions",
            new_callable=AsyncMock,
            return_value=["a"],
        ),
        patch(
            "app.little_legend.vault_erasure_worker.erase_due_private_assets",
            new_callable=AsyncMock,
            return_value={"deleted": 1, "failed": 0},
        ) as worker,
        patch(
            "app.little_legend.vault_operations.retention_health",
            new_callable=AsyncMock,
            return_value={"pending": 0, "oldest_pending_seconds": None},
        ),
    ):
        report = await run_retention_cycle(
            factory, store, now=instant, batch_size=10,
        )
    assert report.queued == 1
    assert report.deleted == 1
    assert report.failed == 0
    assert worker.await_count == 1
    kwargs = worker.await_args.kwargs
    assert kwargs["session_factory"] is factory
    kwargs["deleter"].delete_private_object(
        object_key="little-legend/private/" + "a" * 48,
    )
    store.delete.assert_called_once_with(
        key="little-legend/private/" + "a" * 48,
    )


@pytest.mark.asyncio
async def test_invalid_batch_still_fails_before_database_access():
    factory = Mock()
    with pytest.raises(ValueError, match="batch_size"):
        await run_retention_cycle(factory, Mock(), batch_size=0)
    factory.assert_not_called()
