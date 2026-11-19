"""Operator-only Little Legend legacy budget recovery.

Examples:
 python -m app.little_legend.recover_budgets_cli --limit 100
 python -m app.little_legend.recover_budgets_cli --apply --owner-id 123
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.little_legend.legacy_budget_recovery import recover_legacy_story_budgets


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover inactive legacy story budgets")
    parser.add_argument("--apply", action="store_true", help="Persist eligible budgets")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--owner-id", type=int, default=None)
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = await recover_legacy_story_budgets(
        dry_run=not args.apply, limit=args.limit, owner_id=args.owner_id,
    )
    print(json.dumps(result.model_dump(), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
