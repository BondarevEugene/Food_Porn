"""Recovery must not invent a zero balance for previously active stories."""
import pytest

from app.little_legend.legacy_budget_recovery import (
    legacy_budget_is_safe,
    recover_legacy_story_budgets,
)
from app.little_legend.recover_budgets_cli import parse_args


def test_only_untouched_story_is_eligible() -> None:
    assert legacy_budget_is_safe(
        has_budget=False, has_effect=False, has_reservation=False,
        has_writer_job=False, has_illustration_job=False,
    )


@pytest.mark.parametrize(
    "flag",
    [
        "has_budget", "has_effect", "has_reservation",
        "has_writer_job", "has_illustration_job",
    ],
)
def test_any_financial_history_blocks_backfill(flag: str) -> None:
    flags = dict(
        has_budget=False, has_effect=False, has_reservation=False,
        has_writer_job=False, has_illustration_job=False,
    )
    flags[flag] = True
    assert not legacy_budget_is_safe(**flags)


def test_cli_is_dry_run_by_default() -> None:
    args = parse_args([])
    assert not args.apply
    assert args.limit == 100


def test_cli_requires_explicit_apply() -> None:
    args = parse_args(["--apply", "--owner-id", "123"])
    assert args.apply
    assert args.owner_id == 123


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "owner_id"),
    [(0, None), (501, None), (True, None), (100, 0), (100, -1)],
)
async def test_invalid_batch_rejected_before_database(
    limit: int, owner_id: int | None,
) -> None:
    with pytest.raises(ValueError):
        await recover_legacy_story_budgets(
            dry_run=True, limit=limit, owner_id=owner_id,
        )
