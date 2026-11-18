"""Pure owner portfolio cost rollup and safe API delegation."""
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.little_legend import router as legend_router
from app.little_legend.portfolio_cost_summary import summarize_portfolio
from app.little_legend.story_cost_summary import StoryCostSummary


def test_portfolio_costs_keep_estimates_and_confirmed_separate():
    reports = [
        StoryCostSummary(
            story_id=1, estimated_usd=Decimal("0.50"),
            confirmed_usd=Decimal("0.125"), unreconciled_dispatched_jobs=2,
            chapters=[],
        ),
        StoryCostSummary(
            story_id=2, estimated_usd=Decimal("0.25"),
            confirmed_usd=Decimal("0.000"), chapters=[],
        ),
    ]
    summary = summarize_portfolio(7, reports)
    assert summary.estimated_usd == Decimal("0.75")
    assert summary.confirmed_usd == Decimal("0.125")
    assert summary.unreconciled_dispatched_jobs == 2
    assert len(summary.stories) == 2


def test_portfolio_rejects_duplicate_stories():
    report = StoryCostSummary(story_id=1, chapters=[])
    with pytest.raises(ValueError, match="duplicate"):
        summarize_portfolio(7, [report, report])


@pytest.mark.asyncio
async def test_portfolio_api_passes_authenticated_owner(monkeypatch):
    service = AsyncMock(return_value={"owner_id": 7, "stories": []})
    monkeypatch.setattr(legend_router, "get_portfolio_cost_summary", service)
    result = await legend_router.read_portfolio_costs(owner=7)
    assert result["owner_id"] == 7
    service.assert_awaited_once_with(owner_id=7)
