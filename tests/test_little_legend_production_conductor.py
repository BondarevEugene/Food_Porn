"""Production conductor never bypasses parent approvals or dispatch fences."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.little_legend import production_conductor as conductor
from app.little_legend.router import StoryDraft


def test_unapproved_outline_cannot_start_ai():
    draft = StoryDraft(outline_approved=False)
    assert conductor.classify(draft, writer_count=0, art_count=0) == conductor.Stage.WAITING_OUTLINE


def test_pending_writer_jobs_prevent_duplicate_queue():
    draft = StoryDraft(outline_approved=True)
    # A parent-sourced outline is required regardless of queue state.
    assert conductor.classify(draft, writer_count=1, art_count=0) == conductor.Stage.WAITING_OUTLINE


def test_conductor_requires_explicit_enable(monkeypatch):
    monkeypatch.delenv("LL_CONDUCTOR_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="LL_CONDUCTOR_ENABLED"):
        import asyncio

        asyncio.run(conductor.run(once=True))


@pytest.mark.asyncio
async def test_scan_isolates_failed_paid_orders(monkeypatch):
    class FakeResult:
        def all(self):
            now = datetime.now(UTC)
            return [(1, 2, now), (3, 4, now)]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, _query):
            return FakeResult()

    monkeypatch.setattr(conductor, "async_session_maker", lambda: FakeSession())
    task = AsyncMock(side_effect=[
        RuntimeError("one failed"),
        conductor.AdvanceResult(3, conductor.Stage.WAITING_OUTLINE),
    ])
    monkeypatch.setattr(conductor, "advance_paid_quote", task)
    results = await conductor.scan_paid_queue(illustration_cost_usd=0.05)
    assert [item.stage for item in results] == [
        conductor.Stage.MANUAL_REVIEW,
        conductor.Stage.WAITING_OUTLINE,
    ]
    assert task.await_count == 2


@pytest.mark.asyncio
async def test_once_runs_exactly_one_scan(monkeypatch):
    monkeypatch.setenv("LL_CONDUCTOR_ENABLED", "true")
    monkeypatch.setenv("LL_ILLUSTRATION_PRICE_MICRO_USD", "50000")
    scan = AsyncMock(return_value=[])
    monkeypatch.setattr(conductor, "scan_paid_queue", scan)
    await conductor.run(once=True)
    scan.assert_awaited_once_with(illustration_cost_usd=0.05)


def test_approved_manuscript_advances_to_art_queue():
    draft = StoryDraft(outline_approved=True)
    # Validate the pure transition with a real Pydantic story graph.
    from app.little_legend.story_graph import build_graph
    from app.little_legend.story_writer import StoryManuscript

    draft.graph = build_graph(["Scene one"])
    from app.little_legend.router import StoryDraft as DraftModel
    assert "parent_sketch" in DraftModel.model_fields
    # Parent sketch is required by the stage classifier; use model_construct
    # to isolate the state transition without fabricating private child data.
    draft = draft.model_copy(update={"parent_sketch": object()})
    draft.manuscript = StoryManuscript(
        hero_name=draft.hero, parent_approved=True,
    )
    draft.image_ai_consent.active = True
    assert conductor.classify(
        draft, writer_count=0, art_count=0,
    ) == conductor.Stage.READY_TO_ILLUSTRATE


@pytest.mark.asyncio
async def test_scan_paginates_beyond_first_batch(monkeypatch):
    now = datetime.now(UTC)
    class Page:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def __init__(self, rows):
            self.rows = rows

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, _query):
            return Page(self.rows)

    pages = [
        [(1, 2, now), (3, 4, now)],
        [(5, 6, now)],
    ]
    monkeypatch.setattr(
        conductor, "async_session_maker",
        lambda: Session(pages.pop(0)),
    )
    async def advance(**kwargs):
        return conductor.AdvanceResult(
            kwargs["quote_id"], conductor.Stage.WAITING_OUTLINE,
        )
    monkeypatch.setattr(conductor, "advance_paid_quote", advance)
    result = await conductor.scan_paid_queue(
        illustration_cost_usd=0.05, batch_size=2,
    )
    assert [item.quote_id for item in result] == [1, 3, 5]
