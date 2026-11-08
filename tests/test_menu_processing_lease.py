"""Behavioral tests for distributed processing lease orchestration."""

from unittest.mock import AsyncMock

import pytest

from app.services.menu_processing_lease import MenuProcessingLease
from app.workers.menu_pipeline import MenuPipeline


@pytest.mark.asyncio
async def test_lease_rejected_skips_generation(monkeypatch) -> None:
    class RejectedLease:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return False

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("app.workers.menu_pipeline.MenuProcessingLease", RejectedLease)
    pipeline = object.__new__(MenuPipeline)
    pipeline.session_factory = object()
    pipeline._active_menu_ids = set()
    pipeline._process_unlocked = AsyncMock()

    await pipeline._process(51)

    pipeline._process_unlocked.assert_not_awaited()
    assert pipeline._active_menu_ids == set()


@pytest.mark.asyncio
async def test_lease_release_only_after_processing(monkeypatch) -> None:
    events = []

    class AcceptedLease:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            events.append("acquired")
            return True

        async def __aexit__(self, *args):
            events.append("released")

    monkeypatch.setattr("app.workers.menu_pipeline.MenuProcessingLease", AcceptedLease)
    pipeline = object.__new__(MenuPipeline)
    pipeline.session_factory = object()
    pipeline._active_menu_ids = set()

    async def process(menu_id):
        events.append("generated")

    pipeline._process_unlocked = AsyncMock(side_effect=process)
    await pipeline._process(51)

    assert events == ["acquired", "generated", "released"]
    assert pipeline._active_menu_ids == set()


@pytest.mark.asyncio
async def test_lease_releases_on_exception(monkeypatch) -> None:
    events = []

    class AcceptedLease:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return True

        async def __aexit__(self, *args):
            events.append("released")

    monkeypatch.setattr("app.workers.menu_pipeline.MenuProcessingLease", AcceptedLease)
    pipeline = object.__new__(MenuPipeline)
    pipeline.session_factory = object()
    pipeline._active_menu_ids = set()
    pipeline._process_unlocked = AsyncMock(side_effect=RuntimeError("generation failed"))

    with pytest.raises(RuntimeError, match="generation failed"):
        await pipeline._process(51)

    assert events == ["released"]
    assert pipeline._active_menu_ids == set()
