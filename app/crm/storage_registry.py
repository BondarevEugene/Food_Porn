"""Read-only multibot S3 storage registry.

Optional CRM_STORAGE_CONNECTIONS_JSON is a JSON array of non-secret connection
definitions. Credentials are resolved exclusively from server environment names.
A shared bucket must use disjoint prefixes per bot to avoid double counting.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_BOT = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]{2,99}$")


def extra_connections(env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    values = os.environ if env is None else env
    raw = values.get("CRM_STORAGE_CONNECTIONS_JSON", "")
    if not raw:
        return []
    try:
        configs = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid storage registry JSON") from exc
    if not isinstance(configs, list) or len(configs) > 30:
        raise ValueError("Storage registry must contain up to 30 connections")
    result = []
    for entry in configs:
        if not isinstance(entry, dict):
            raise ValueError("Invalid storage connection")
        bot_id = entry.get("bot_id")
        name = entry.get("name")
        prefix = entry.get("prefix")
        if (
            not isinstance(bot_id, str) or not _BOT.fullmatch(bot_id)
            or not isinstance(name, str) or not 1 <= len(name) <= 60
            or not isinstance(prefix, str) or not prefix.endswith("/")
            or prefix.startswith("/") or ".." in prefix
            or not re.fullmatch(r"[a-zA-Z0-9/_-]{2,100}", prefix)
        ):
            raise ValueError("Invalid bot, connection name or object prefix")
        env_fields = {}
        for key in ("endpoint", "bucket", "region", "access", "secret"):
            variable = entry.get(key + "_env")
            if not isinstance(variable, str) or not _ENV.fullmatch(variable):
                raise ValueError("Storage registry must reference environment variables")
            env_fields[key] = values.get(variable, "")
        if not all(env_fields.values()) or not env_fields["endpoint"].startswith(
            "https://"
        ):
            # Misconfigured connections remain visible as errors, not fake zeros.
            result.append({
                "provider": name, "bot_id": bot_id, "prefix": prefix,
                "storage_provider": "S3-compatible", "configured": False,
                "bucket": env_fields["bucket"] or "Не настроено",
            })
            continue
        result.append({
            **env_fields, "provider": name, "bot_id": bot_id,
            "prefix": prefix, "storage_provider": "S3-compatible",
            "configured": True,
        })
    # Same bucket may be shared, but object namespaces must never overlap.
    for i, left in enumerate(result):
        for right in result[i + 1:]:
            if (
                left.get("endpoint") == right.get("endpoint")
                and left["bucket"] == right["bucket"]
                and (
                    left["prefix"].startswith(right["prefix"])
                    or right["prefix"].startswith(left["prefix"])
                )
            ):
                raise ValueError("Overlapping storage prefixes in shared bucket")
    return result
