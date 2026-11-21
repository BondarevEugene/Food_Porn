"""Read-only R2/Neon reconciliation; unknown objects are always protected."""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.storage_artifacts import artifacts


async def registry_snapshot(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(
        artifacts.c.bot_id, artifacts.c.connection, artifacts.c.bucket,
        artifacts.c.object_key, artifacts.c.bytes, artifacts.c.etag,
        artifacts.c.state, artifacts.c.retention_hold,
    ))).mappings().all()
    return [dict(row) for row in rows]


def reconcile(
    inventory: dict[str, Any], registry: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare only complete provider listings. Never authorize deletion."""
    registered = {
        (r["bot_id"], r["bucket"], r["object_key"]): r
        for r in registry
    }
    observed: set[tuple[str, str, str]] = set()
    findings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    complete = True
    complete_scopes: list[tuple[str, str, str]] = []
    for provider in inventory.get("providers", []):
        ok = provider.get("status") == "ok" and not provider.get("truncated")
        if not ok:
            complete = False
            counts["unavailable_providers"] += 1
            continue
        bot_id = provider["bot_id"]
        connection = provider["provider"]
        bucket = provider["bucket"]
        prefix = provider.get("prefix", "")
        complete_scopes.append((bot_id, bucket, prefix))
        for obj in provider.get("objects", []):
            object_key = obj["key"]
            key = (bot_id, bucket, object_key)
            # Shared buckets may be listed by multiple connections.
            if key in observed:
                continue
            observed.add(key)
            row = registered.get(key)
            if row is None:
                status = "unregistered"
            elif row["state"] == "deleted":
                status = "unexpected_after_delete"
            elif row["bytes"] != obj["bytes"]:
                status = "size_mismatch"
            else:
                status = "registered"
            counts[status] += 1
            if status != "registered":
                findings.append({
                    "bot_id": bot_id, "provider": connection, "bucket": bucket,
                    "key": object_key, "status": status, "protected": True,
                })
    # Missing means absent from a COMPLETE listing covering the key prefix.
    # A partial or unrelated connection must never establish absence.
    for key, row in registered.items():
        if (
            key not in observed and row["state"] != "deleted"
            and any(
                bot == key[0] and bucket == key[1] and key[2].startswith(prefix)
                for bot, bucket, prefix in complete_scopes
            )
        ):
            counts["missing_in_r2"] += 1
            findings.append({
                "bot_id": key[0], "provider": row["connection"], "bucket": key[1],
                "key": key[2], "status": "missing_in_r2", "protected": True,
            })
    return {
        "status": "complete" if complete and inventory.get("providers") else "partial",
        "counts": dict(counts),
        "findings": findings[:500],
        "findings_truncated": len(findings) > 500,
        "deletion_enabled": False,
        "message": "Только сверка. Неизвестные и спорные файлы защищены.",
    }
