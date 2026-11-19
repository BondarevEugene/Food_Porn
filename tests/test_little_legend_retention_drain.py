"""PostgreSQL retention drain coordination and bounded retries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.little_legend.retention_drain import drain_retention


def fake_engine(*, locked=True, dialect="postgresql"):
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=[
        SimpleNamespace(scalar_one=lambda: locked),
        SimpleNamespace(),
    ])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    engine = MagicMock()
    engine.dialect.name = dialect
    engine.connect.return_value = ctx
    return engine, conn


@pytest.mark.asyncio
async def test_rejects_non_postgres_before_connecting():
    engine, _ = fake_engine(dialect="sqlite")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        await drain_retention(engine=engine, deleter=MagicMock())
    engine.connect.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_invalid_cycle_count():
    engine, _ = fake_engine()
    with pytest.raises(ValueError, match="max_cycles"):
        await drain_retention(
            engine=engine, deleter=MagicMock(), max_cycles=21,
        )
    engine.connect.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_worker_does_not_delete():
    engine, conn = fake_engine(locked=False)
    with patch(
        "app.little_legend.retention_drain.run_private_retention_cycle",
        new_callable=AsyncMock,
    ) as worker:
        result = await drain_retention(engine=engine, deleter=MagicMock())
    assert result.status == "already_running"
    assert result.cycles == 0
    worker.assert_not_awaited()
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_drain_is_bounded_and_releases_lock():
    engine, conn = fake_engine()
    report = SimpleNamespace(
        expired_queued=25, physically_deleted=25,
        deletion_failed=0, more_work_possible=True,
    )
    with patch(
        "app.little_legend.retention_drain.run_private_retention_cycle",
        new_callable=AsyncMock, return_value=report,
    ) as worker:
        result = await drain_retention(
            engine=engine, deleter=MagicMock(), max_cycles=3,
        )
    assert result.cycles == 3
    assert result.physically_deleted == 75
    assert result.more_work_possible
    assert worker.await_count == 3
    assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_failure_releases_advisory_lock():
    engine, conn = fake_engine()
    with patch(
        "app.little_legend.retention_drain.run_private_retention_cycle",
        new_callable=AsyncMock, side_effect=RuntimeError("storage down"),
    ):
        with pytest.raises(RuntimeError, match="storage down"):
            await drain_retention(engine=engine, deleter=MagicMock())
    assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_no_progress_stops_without_busy_loop():
    engine, _ = fake_engine()
    report = SimpleNamespace(
        expired_queued=0, physically_deleted=0,
        deletion_failed=1, more_work_possible=True,
    )
    with patch(
        "app.little_legend.retention_drain.run_private_retention_cycle",
        new_callable=AsyncMock, return_value=report,
    ) as worker:
        result = await drain_retention(engine=engine, deleter=MagicMock())
    assert result.cycles == 1
    worker.assert_awaited_once()
