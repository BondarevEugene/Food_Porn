"""Book budget configuration is bounded and fails closed."""
import pytest

from app.little_legend.story_budget_provision import (
    DEFAULT_BOOK_BUDGET_MICRO_USD,
    MAX_BOOK_BUDGET_MICRO_USD,
    configured_book_budget_micro_usd,
    provision_story_budget,
)


def test_default_budget_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITTLE_LEGEND_BOOK_AI_BUDGET_MICRO_USD", raising=False)
    assert configured_book_budget_micro_usd() == DEFAULT_BOOK_BUDGET_MICRO_USD


@pytest.mark.parametrize("raw", ["", "0", "-1", "nope", "20000001"])
def test_invalid_budget_rejected(
    monkeypatch: pytest.MonkeyPatch, raw: str,
) -> None:
    monkeypatch.setenv("LITTLE_LEGEND_BOOK_AI_BUDGET_MICRO_USD", raw)
    with pytest.raises(ValueError, match="budget"):
        configured_book_budget_micro_usd()


def test_configured_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "LITTLE_LEGEND_BOOK_AI_BUDGET_MICRO_USD",
        str(MAX_BOOK_BUDGET_MICRO_USD),
    )
    assert configured_book_budget_micro_usd() == MAX_BOOK_BUDGET_MICRO_USD


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("story_id", "owner_id", "limit"),
    [(0, 1, 100), (1, 0, 100), (1, 1, 0), (1, 1, 20_000_001)],
)
async def test_invalid_identity_never_touches_database(
    story_id: int, owner_id: int, limit: int,
) -> None:
    with pytest.raises(ValueError, match="Invalid story budget"):
        await provision_story_budget(
            None, story_id=story_id, owner_id=owner_id,
            limit_micro_usd=limit,
        )
