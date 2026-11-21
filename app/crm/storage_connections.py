"""Database-backed non-secret S3 connection definitions for Mini CRM.

Uses the existing AppSetting table, requiring no migration. Railway environment
variables remain the only source of S3 credentials.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.storage_registry import extra_connections
from app.database.models import AppSetting

KEY = "crm_storage_connections_json"


async def load(session: AsyncSession) -> list[dict[str, Any]]:
    setting = await session.get(AppSetting, KEY)
    if setting is None:
        return []
    try:
        payload = json.loads(setting.value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Corrupt stored storage registry") from exc
    if not isinstance(payload, list):
        raise ValueError("Invalid stored storage registry")
    return payload


def validate(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate shape, env references and shared-bucket prefix isolation."""
    raw = json.dumps(entries)
    extra_connections({"CRM_STORAGE_CONNECTIONS_JSON": raw})
    return entries


async def save(session: AsyncSession, entries: list[dict[str, Any]]) -> None:
    validate(entries)
    setting = await session.get(AppSetting, KEY)
    if setting is None:
        session.add(AppSetting(
            key=KEY, value=json.dumps(entries),
            description="S3 storage connections: env variable references only",
        ))
    else:
        setting.value = json.dumps(entries)


def resolve(entries: list[dict[str, Any]], env: dict[str, str]) -> list[dict[str, Any]]:
    """Resolve stored entries without exposing secrets to the API."""
    values = dict(env)
    values["CRM_STORAGE_CONNECTIONS_JSON"] = json.dumps(entries)
    return extra_connections(values)
