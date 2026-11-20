"""Minimal privacy-safe Telegram notification transport for retention alerts.

Never include identifiers, object keys, photos or exception messages.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

_ALLOWED_CODES = frozenset({
    "RETENTION_EXPIRED_BACKLOG",
    "RETENTION_PENDING_OVER_24H",
    "RETENTION_RETRY_EXHAUSTED",
    "RETENTION_DELETE_FAILED",
})


def alert_message(operations: Mapping[str, Any]) -> str | None:
    """Build a bounded message using only known alert codes and severity."""
    if operations.get("status") == "ok":
        return None
    status = operations.get("status")
    if status not in {"warning", "critical"}:
        raise ValueError("Invalid alert status")
    raw_codes = operations.get("codes")
    if not isinstance(raw_codes, (list, tuple)):
        raise ValueError("Invalid alert codes")
    if any(code not in _ALLOWED_CODES for code in raw_codes):
        raise ValueError("Unknown alert code")
    codes = sorted(set(raw_codes))
    if not codes:
        raise ValueError("Non-healthy status requires alert codes")
    return "Little Legend retention: " + status.upper() + "\n" + "\n".join(codes)


async def notify_retention(
    operations: Mapping[str, Any], *,
    token: str | None = None, chat_id: str | None = None,
) -> bool:
    """Send an opt-in owner alert. Returns False for healthy or unconfigured."""
    message = alert_message(operations)
    if message is None:
        return False
    token = token if token is not None else os.environ.get(
        "LITTLE_LEGEND_ALERT_BOT_TOKEN", "",
    )
    chat_id = chat_id if chat_id is not None else os.environ.get(
        "LITTLE_LEGEND_ALERT_CHAT_ID", "",
    )
    if not token or not chat_id:
        return False
    if not token.replace(":", "").replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid Telegram token")
    if not chat_id.lstrip("-").isdigit():
        raise ValueError("Invalid Telegram chat ID")
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message,
                  "disable_web_page_preview": True},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok") is not True:
            raise RuntimeError("Telegram notification not acknowledged")
    return True
