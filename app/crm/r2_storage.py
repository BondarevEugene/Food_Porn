"""Owner-only Cloudflare R2 inventory for the Mini CRM.

Only configured private Little Legend buckets are inspected. No credentials,
presigned links, object bodies or customer content leave this module.
"""
from __future__ import annotations

import os
from datetime import UTC
from typing import Any

from fastapi import HTTPException

from app.crm.storage_registry import extra_connections

PREFIX = "little-legend/"
MAX_OBJECTS = 5000


def configured_targets(env: dict[str, str] | None = None) -> list[dict[str, str]]:
    values = os.environ if env is None else env
    specs = (
        ("release", "LITTLE_LEGEND_S3_ENDPOINT_URL", "LITTLE_LEGEND_S3_BUCKET",
         "LITTLE_LEGEND_S3_REGION", "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
         "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY"),
        ("illustrations", "LITTLE_LEGEND_ART_S3_ENDPOINT", "LITTLE_LEGEND_ART_S3_BUCKET",
         "LITTLE_LEGEND_ART_S3_REGION", "LITTLE_LEGEND_ART_S3_ACCESS_KEY",
         "LITTLE_LEGEND_ART_S3_SECRET_KEY"),
    )
    result = []
    for label, endpoint, bucket, region, access, secret in specs:
        fields = (values.get(endpoint, ""), values.get(bucket, ""),
                  values.get(region, ""), values.get(access, ""),
                  values.get(secret, ""))
        if all(fields) and fields[0].startswith("https://"):
            result.append(dict(zip(
                ("endpoint", "bucket", "region", "access", "secret"), fields, strict=True,
            ), provider=label))
    for target in result:
        target.update({
            "bot_id": "little_legend", "prefix": PREFIX,
            "storage_provider": "Cloudflare R2", "configured": True,
        })
    extras = extra_connections(values)
    for extra in extras:
        for legacy in result:
            if (
                extra.get("endpoint") == legacy.get("endpoint")
                and extra["bucket"] == legacy["bucket"]
                and (
                    extra["prefix"].startswith(legacy["prefix"])
                    or legacy["prefix"].startswith(extra["prefix"])
                )
            ):
                raise ValueError("Storage registry overlaps a legacy Little Legend bucket")
    result.extend(extras)
    return result


def client_for(target: dict[str, str]):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", endpoint_url=target["endpoint"], region_name=target["region"],
        aws_access_key_id=target["access"], aws_secret_access_key=target["secret"],
        config=Config(connect_timeout=5, read_timeout=12, retries={"max_attempts": 2}),
    )


def inventory(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return explicit per-connection status, never silently label failure as zero."""
    providers: list[dict[str, Any]] = []
    targets = configured_targets(env)
    for target in targets:
        base = {
            "provider": target["provider"], "bucket": target["bucket"],
            "bot_id": target.get("bot_id", "little_legend"),
            "prefix": target.get("prefix", PREFIX),
            "storage_provider": target.get("storage_provider", "Cloudflare R2"),
            "capacity_bytes": None, "free_bytes": None,
        }
        try:
            if not target.get("configured", True):
                raise ValueError("Storage connection is not configured")
            client = client_for(target)
            objects: list[dict[str, Any]] = []
            cursor = None
            truncated = False
            while True:
                args = {
                    "Bucket": target["bucket"], "Prefix": target.get("prefix", PREFIX), "MaxKeys": 1000,
                }
                if cursor:
                    args["ContinuationToken"] = cursor
                response = client.list_objects_v2(**args)
                for item in response.get("Contents", []):
                    key = item["Key"]
                    if key.startswith(target.get("prefix", PREFIX) + "diagnostics/"):
                        continue
                    modified = item["LastModified"]
                    objects.append({
                        "key": key, "bytes": int(item["Size"]),
                        "created_at": modified.astimezone(UTC).isoformat(),
                        "etag": str(item.get("ETag", "")).strip('"'),
                    })
                    if len(objects) >= MAX_OBJECTS:
                        truncated = True
                        break
                if truncated or not response.get("IsTruncated"):
                    break
                cursor = response.get("NextContinuationToken")
                if not cursor:
                    raise RuntimeError("Missing inventory pagination cursor")
            providers.append({
                **base, "status": "partial" if truncated else "ok",
                "objects": objects, "used_bytes": sum(x["bytes"] for x in objects),
                "object_count": len(objects), "truncated": truncated,
            })
        except Exception:
            # Never expose endpoint URLs, tokens or exception details in CRM.
            providers.append({
                **base, "status": "error", "objects": [],
                "used_bytes": None, "object_count": None,
                "truncated": False,
                "error": "Не удалось прочитать бакет. Проверьте подключение и права R2.",
            })
    healthy = [p for p in providers if p["status"] == "ok"]
    complete = len(healthy) == len(providers) and bool(providers)
    return {
        "providers": providers,
        "bots": [
            {"id": bot, "label": "Little Legend" if bot == "little_legend" else bot.replace("_", " ").title()}
            for bot in dict.fromkeys(p["bot_id"] for p in providers)
        ],
        "total_used_bytes": (
            sum(p["used_bytes"] for p in healthy) if complete else None
        ),
        "status": "ok" if complete else "not_configured" if not providers else "partial",
        "note": (
            "R2 не сообщает физически свободный объём бакета. "
            "Подсчёт ограничен префиксами настроенных подключений."
        ),
    }


def delete_selected(*, provider: str, keys: list[str],
                    env: dict[str, str] | None = None) -> dict[str, Any]:
    if not keys or len(keys) > 100 or len(set(keys)) != len(keys):
        raise HTTPException(422, "Select 1 to 100 distinct files")
    targets = {x["provider"]: x for x in configured_targets(env)}
    target = targets.get(provider)
    if target is None:
        raise HTTPException(404, "Storage provider not configured")
    # No bulk prefix deletion, diagnostic objects or arbitrary S3 paths.
    if any(not key.startswith(PREFIX) or key.startswith(
        "little-legend/diagnostics/"
    ) or ".." in key or len(key) > 1024 for key in keys):
        raise HTTPException(422, "Invalid object selection")
    client = client_for(target)
    deleted = 0
    for key in keys:
        client.delete_object(Bucket=target["bucket"], Key=key)
        deleted += 1
    return {"deleted": deleted, "provider": provider}
