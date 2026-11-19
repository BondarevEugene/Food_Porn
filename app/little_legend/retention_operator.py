"""Opt-in, one-shot private retention operator command.

Usage: python -m app.little_legend.retention_operator --dry-run
       python -m app.little_legend.retention_operator --execute

Do not schedule until private S3 credentials and operational alerts are reviewed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict

from app.database.session import async_session_maker
from app.little_legend.privacy_lifecycle import PrivacyLaunchConfig
from app.little_legend.vault_operator_audit import audit_private_vault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Little Legend private vault operator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    return parser


async def run_operator(*, execute: bool, batch_size: int) -> dict[str, object]:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    if execute and os.environ.get("LITTLE_LEGEND_RETENTION_EXECUTE") != "YES":
        raise PermissionError("Explicit operator execution approval is required")
    if execute:
        import boto3

        from app.little_legend.vault_erasure_worker import S3PrivateObjectDeleter
        from app.little_legend.vault_retention_cycle import (
            run_private_retention_cycle,
        )

        bucket = os.environ.get("LITTLE_LEGEND_PRIVATE_BUCKET", "").strip()
        if not bucket:
            raise ValueError("Private S3 bucket is not configured")
        client = boto3.client("s3")
        deleter = S3PrivateObjectDeleter(client=client, bucket=bucket)
        report = await run_private_retention_cycle(
            deleter=deleter, batch_size=batch_size,
        )
        result: dict[str, object] = {"retention": asdict(report)}
        result["retention"]["completed_at"] = report.completed_at.isoformat()
    else:
        result = {"mode": "dry-run", "storage_mutated": False}
    async with async_session_maker() as session:
        audit = await audit_private_vault(
            session, config=PrivacyLaunchConfig(),
        )
    result["audit"] = asdict(audit)
    return result


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(
            run_operator(execute=args.execute, batch_size=args.batch_size)
        )
    except (PermissionError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
