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
        (r["bot_id"], r["connection"], r["bucket"], r["object_key"]): r
        for r in registry
    }
    observed: set[tuple[str, str, str, str]] = set()
    findings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    complete = True
    for provider in inventory.get("providers", []):
        ok = provider.get("status") == "ok" and not provider.get("truncated")
        if not ok:
            complete = False
            counts["unavailable_providers"] += 1
            continue
        bot_id = provider["bot_id"]
        connection = provider["provider"]
        bucket = provider["bucket"]
        for obj in provider.get("objects", []):
            key = (bot_id, connection, bucket, obj["key"])
            observed.add(key)
            row = registered.get(key)
            if row is None:
                status = "unregistered"
            elif row["state"] == "deleted":
                status = "unexpected_after_delete"
            elif row["bytes"] != obj["bytes"]:
                status = "size_mismatch"
            elif row.get("etag") and row["etag"] != obj.get("etag"):
                # PDF registry stores SHA-256, which is not an S3 ETag.
                status = "registered"
            else:
                status = "registered"
            counts[status] += 1
            if status != "registered":
                findings.append({
                    "bot_id": bot_id, "provider": connection, "bucket": bucket,
                    "key": obj["key"], "status": status, "protected": True,
                })
    # Only a fully enumerated provider can prove an object absent.
    complete_providers = {
        (p["bot_id"], p["provider"], p["bucket"])
        for p in inventory.get("providers", [])
        if p.get("status") == "ok" and not p.get("truncated")
    }
    for key, row in registered.items():
        if key[:3] in complete_providers and key not in observed and row["state"] != "deleted":
            counts["missing_in_r2"] += 1
            findings.append({
                "bot_id": key[0], "provider": key[1], "bucket": key[2],
                "key": key[3], "status": "missing_in_r2", "protected": True,
            })
    return {
        "status": "complete" if complete and inventory.get("providers") else "partial",
        "counts": dict(counts),
        "findings": findings[:500],
        "findings_truncated": len(findings) > 500,
        "deletion_enabled": False,
        "message": "Только сверка. Неизвестные и спорные файлы защищены.",
    }
