"""Storage usage aggregation for bot tabs and shared S3 providers.

Only sum non-overlapping, complete inventories. Unknown usage stays unknown.
"""
from __future__ import annotations

from typing import Any


def summarize(providers: list[dict[str, Any]]) -> dict[str, Any]:
    bots: dict[str, dict[str, Any]] = {}
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for p in providers:
        bot_id = p["bot_id"]
        bot = bots.setdefault(bot_id, {
            "bot_id": bot_id, "connections": 0, "healthy": 0,
            "object_count": 0, "used_bytes": 0, "status": "ok",
        })
        bot["connections"] += 1
        good = p["status"] == "ok"
        if good:
            bot["healthy"] += 1
            if bot["object_count"] is not None:
                bot["object_count"] += p["object_count"]
            if bot["used_bytes"] is not None:
                bot["used_bytes"] += p["used_bytes"]
        else:
            bot["used_bytes"] = None
            bot["object_count"] = None
            bot["status"] = "partial"
        key = (p["storage_provider"], p["bucket"])
        bucket = buckets.setdefault(key, {
            "provider": p["storage_provider"], "bucket": p["bucket"],
            "bots": set(), "connections": 0, "used_bytes": 0,
            "object_count": 0, "status": "ok",
        })
        bucket["bots"].add(bot_id)
        bucket["connections"] += 1
        if good:
            if bucket["used_bytes"] is not None:
                bucket["used_bytes"] += p["used_bytes"]
            if bucket["object_count"] is not None:
                bucket["object_count"] += p["object_count"]
        else:
            bucket["used_bytes"] = None
            bucket["object_count"] = None
            bucket["status"] = "partial"
    return {
        "bot_usage": sorted(bots.values(), key=lambda item: item["bot_id"]),
        "bucket_usage": [
            {**item, "bots": sorted(item["bots"])}
            for item in sorted(buckets.values(), key=lambda item: (
                item["provider"], item["bucket"],
            ))
        ],
    }
