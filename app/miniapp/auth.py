"""Validate the signed Telegram Mini App launch payload on every API request."""
from __future__ import annotations

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
    if scheme.lower() != "tma" or not raw:
        raise HTTPException(status_code=401, detail="Open this page from the Telegram bot")
    return verify_init_data(raw, get_settings().bot_token)
