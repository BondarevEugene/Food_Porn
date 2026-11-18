"""Cost API never exposes another owner's Little Legend finances."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.little_legend import router as legend_router
from app.little_legend.story_cost_summary import StoryCostSummary


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _query):
        return FakeResult(self.value)


@pytest.mark.asyncio
async def test_cost_api_rejects_other_owner(monkeypatch):
    report = AsyncMock()
    monkeypatch.setattr(legend_router, "async_session_maker", lambda: FakeSession(None))
    monkeypatch.setattr(legend_router, "get_story_cost_summary", report)
    with pytest.raises(HTTPException) as exc:
        await legend_router.read_story_costs(42, owner=7)
    assert exc.value.status_code == 404
    report.assert_not_awaited()


@pytest.mark.asyncio
async def test_cost_api_returns_only_financial_summary(monkeypatch):
    expected = StoryCostSummary(story_id=42, chapters=[])
    report = AsyncMock(return_value=expected)
    monkeypatch.setattr(legend_router, "async_session_maker", lambda: FakeSession(42))
    monkeypatch.setattr(legend_router, "get_story_cost_summary", report)
    actual = await legend_router.read_story_costs(42, owner=7)
    assert actual == expected
    report.assert_awaited_once_with(owner_id=7, story_id=42)
    assert "manuscript" not in actual.model_dump()
