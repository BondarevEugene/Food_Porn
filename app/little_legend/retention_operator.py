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

from app.database.session import async_session_maker, engine
from app.little_legend.privacy_lifecycle import PrivacyLaunchConfig
from app.little_legend.retention_alert_policy import evaluate_retention
from app.little_legend.retention_notifications import alert_message, notify_retention
from app.little_legend.vault_operator_audit import audit_private_vault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Little Legend private vault operator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-cycles", type=int, default=4)
    parser.add_argument("--fail-on-alert", action="store_true")
    parser.add_argument("--notify-owner", action="store_true")
    parser.add_argument("--max-expired", type=int, default=0)
    parser.add_argument("--max-pending-24h", type=int, default=0)
    return parser


async def run_operator(
    *, execute: bool, batch_size: int, max_expired: int = 0,
    max_pending_24h: int = 0, max_cycles: int = 4,
    notify_owner: bool = False,
) -> dict[str, object]:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    if not 1 <= max_cycles <= 20:
        raise ValueError("max_cycles must be 1..20")
    if execute and os.environ.get("LITTLE_LEGEND_RETENTION_EXECUTE") != "YES":
        raise PermissionError("Explicit operator execution approval is required")
    if execute:
        import boto3

        from app.little_legend.retention_drain import drain_retention, drain_to_dict
        from app.little_legend.vault_erasure_worker import S3PrivateObjectDeleter

        bucket = os.environ.get("LITTLE_LEGEND_PRIVATE_BUCKET", "").strip()
        if not bucket:
            raise ValueError("Private S3 bucket is not configured")
        client = boto3.client("s3")
        deleter = S3PrivateObjectDeleter(client=client, bucket=bucket)
        report = await drain_retention(
            engine=engine, deleter=deleter, batch_size=batch_size,
            max_cycles=max_cycles,
        )
        result: dict[str, object] = {"retention": {
            "deletion_failed": report.deletion_failed,
            "expired_queued": report.expired_queued,
            "physically_deleted": report.physically_deleted,
            "more_work_possible": report.more_work_possible,
        }, "drain": drain_to_dict(report)}
    else:
        result = {"mode": "dry-run", "storage_mutated": False}
    async with async_session_maker() as session:
        audit = await audit_private_vault(
            session, config=PrivacyLaunchConfig(),
        )
    result["audit"] = asdict(audit)
    decision = evaluate_retention(
        result["audit"], retention=result.get("retention"),
        max_expired=max_expired, max_pending_24h=max_pending_24h,
    )
    result["operations"] = asdict(decision)
    result["notification"] = {
        "eligible": alert_message(result["operations"]) is not None,
        "requested": notify_owner,
        "sent": False,
    }
    if notify_owner:
        result["notification"]["sent"] = await notify_retention(
            result["operations"],
        )
    return result


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(
            run_operator(
                execute=args.execute, batch_size=args.batch_size,
                max_expired=args.max_expired,
                max_pending_24h=args.max_pending_24h,
                max_cycles=args.max_cycles,
                notify_owner=args.notify_owner,
            )
        )
    except (PermissionError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.fail_on_alert:
        if result.get("drain", {}).get("status") == "already_running":
            raise SystemExit(4)
        raise SystemExit(result["operations"]["exit_code"])


if __name__ == "__main__":
    main()
