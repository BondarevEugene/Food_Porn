"""Telegram signature / browser session authorization and encrypted credentials."""

from __future__ import annotations

import json
import secrets
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.database.session import async_session_maker
from app.miniapp.auth import current_user
from app.services.admin_access import has_admin_access


def credential_cipher() -> Fernet:
    key = get_settings().crm_encryption_key.get_secret_value()
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            503, "CRM_ENCRYPTION_KEY не настроен. Запустите установщик обновления."
        ) from exc


def encrypt_credentials(values: dict) -> str:
    return credential_cipher().encrypt(json.dumps(values).encode()).decode()


def decrypt_credentials(value: str) -> dict:
    if not value:
        return {}
    try:
        return json.loads(credential_cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(
            503, "Не удалось расшифровать ключи. Восстановите исходный CRM_ENCRYPTION_KEY."
        ) from exc


async def crm_identity(request: Request, authorization: Annotated[str, Header()] = "") -> dict:
    if authorization:
        user = current_user(authorization)
        if not await has_admin_access(
            user["id"], user.get("username"), get_settings(), async_session_maker
        ):
            raise HTTPException(403, "Нет доступа к CRM")
        return {
            **user,
            "actor": f"telegram:{user['id']}",
            "owner": user["id"] in get_settings().admin_telegram_ids,
        }
    if request.session.get("admin_authenticated") is True:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            expected = request.session.get("crm_csrf", "")
            supplied = request.headers.get("x-csrf-token", "")
            if not expected or not secrets.compare_digest(expected, supplied):
                raise HTTPException(403, "Обновите страницу и повторите действие")
        return {"actor": "web:admin", "owner": True, "first_name": "Администратор"}
    raise HTTPException(401, "Откройте CRM из Telegram или войдите через /admin/login")


def require_owner(identity: dict) -> None:
    if not identity.get("owner"):
        raise HTTPException(
            403, "Управлять доступом и API-ключами может администратор из ADMIN_TELEGRAM_IDS"
        )
