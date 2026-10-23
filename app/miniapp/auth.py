"""
==========================================================
FOOD_PORN

Module: Mini App Authentication
Layer: Security

Validates Telegram launch data and signed entry links issued to
supported external messaging channels.
==========================================================
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.config import get_settings


def verify_init_data(raw: str, token: str, *, now: int | None = None) -> dict:
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs) or not fields.get("hash") or not token:
            raise ValueError("Missing or duplicate launch fields")
        stamp = int(fields["auth_date"])
        age = (int(time.time()) if now is None else now) - stamp
        if age < -30 or age > 86400:
            raise ValueError("Expired launch payload")
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()) if key != "hash")
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, fields["hash"]):
            raise ValueError("Invalid launch signature")
        user = json.loads(fields["user"])
        if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
            raise ValueError("Invalid user")
        return user
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Open this page from the Telegram bot") from exc


def current_user(authorization: str = Header(default="")) -> dict:
    scheme, _, raw = authorization.partition(" ")
    if not raw:
        raise HTTPException(status_code=401, detail="Open this page from the Telegram bot")
    if scheme.lower() == "tma":
        return verify_init_data(raw, get_settings().bot_token)
    if scheme.lower() == "channel":
        return verify_channel_token(raw)
    raise HTTPException(status_code=401, detail="Open this page from a supported messenger")


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def channel_internal_user_id(channel: str, external_user_id: str) -> int:
    digest = hashlib.sha256(f"{channel}:{external_user_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 62) - 1) or 1


def create_channel_token(
    channel: str,
    external_user_id: str,
    *,
    name: str = "",
    language: str = "en",
    now: int | None = None,
) -> str:
    settings = get_settings()
    secret = settings.channel_link_secret.get_secret_value()
    if not secret:
        raise RuntimeError("CHANNEL_LINK_SECRET is not configured")
    payload = {
        "channel": channel,
        "external_user_id": external_user_id,
        "name": name[:100],
        "language": language[:2],
        "iat": int(time.time()) if now is None else now,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_channel_token(raw: str, *, now: int | None = None) -> dict:
    settings = get_settings()
    secret = settings.channel_link_secret.get_secret_value()
    try:
        encoded, signature = raw.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid signature")
        payload = json.loads(_b64decode(encoded))
        issued = int(payload["iat"])
        age = (int(time.time()) if now is None else now) - issued
        if age < -30 or age > settings.channel_link_ttl_hours * 3600:
            raise ValueError("Expired link")
        channel = str(payload["channel"])
        external_id = str(payload["external_user_id"])
        if channel not in {"whatsapp", "messenger", "instagram", "viber", "slack", "discord"}:
            raise ValueError("Unknown channel")
        return {
            "id": channel_internal_user_id(channel, external_id),
            "first_name": str(payload.get("name") or "Customer"),
            "language_code": str(payload.get("language") or "en")[:2],
            "source_channel": channel,
            "external_user_id": external_id,
        }
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="This messenger link is invalid or expired") from exc
