"""Concurrent menu processing attempts must not double-spend within one process."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.workers.menu_pipeline import MenuPipeline


@pytest.mark.asyncio
async def test_duplicate_menu_is_not_processed_concurrently() -> None:
    pipeline = object.__new__(MenuPipeline)
    pipeline._active_menu_ids = set()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def process(menu_id: int) -> None:
        entered.set()
        await release.wait()

    pipeline._process_unlocked = AsyncMock(side_effect=process)
    first = asyncio.create_task(pipeline._process(92))
    await entered.wait()
    await pipeline._process(92)
    assert pipeline._process_unlocked.await_count == 1
    release.set()
    await first
    assert pipeline._active_menu_ids == set()


@pytest.mark.asyncio
async def test_failed_processing_releases_menu_id() -> None:
    pipeline = object.__new__(MenuPipeline)
    pipeline._active_menu_ids = set()
    pipeline._process_unlocked = AsyncMock(side_effect=RuntimeError("failed"))
    with pytest.raises(RuntimeError, match="failed"):
        await pipeline._process(92)
    assert pipeline._active_menu_ids == set()


@pytest.mark.asyncio
async def test_distinct_menus_can_run_concurrently() -> None:
    pipeline = object.__new__(MenuPipeline)
    pipeline._active_menu_ids = set()
    entered = set()
    release = asyncio.Event()

    async def process(menu_id: int) -> None:
        entered.add(menu_id)
        if len(entered) == 2:
            release.set()
        await release.wait()

    pipeline._process_unlocked = AsyncMock(side_effect=process)
    await asyncio.wait_for(
        asyncio.gather(pipeline._process(92), pipeline._process(93)), timeout=2
    )
    assert entered == {92, 93}
    assert pipeline._active_menu_ids == set()
