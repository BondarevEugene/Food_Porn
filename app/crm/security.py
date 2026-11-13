
"""Telegram authorization, browser sessions and encrypted CRM credentials."""

from __future__ import annotations

import json
import secrets
import time
from typing import Annotated, Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.miniapp.auth import current_user


def credential_cipher() -> Fernet:
    """Create a Fernet cipher using the configured CRM encryption key."""
    raw_key = get_settings().crm_encryption_key.get_secret_value().strip()

    if not raw_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "CRM_ENCRYPTION_KEY не настроен. "
                "Проверьте конфигурацию сервера."
            ),
        )

    try:
        return Fernet(raw_key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "CRM_ENCRYPTION_KEY имеет неверный формат. "
                "Укажите корректный Fernet-ключ."
            ),
        ) from exc


def encrypt_credentials(values: dict[str, Any]) -> str:
    """Encrypt integration credentials before storing them in the database."""
    if not isinstance(values, dict):
        raise TypeError("Credentials must be a dictionary")

    try:
        payload = json.dumps(
            values,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Credentials contain unsupported values"
        ) from exc

    return credential_cipher().encrypt(payload).decode("ascii")


def decrypt_credentials(value: str | None) -> dict[str, Any]:
    """Decrypt integration credentials stored in the database."""
    if not value:
        return {}

    if not isinstance(value, str):
        raise HTTPException(
            status_code=503,
            detail="Сохранённые CRM-ключи имеют неверный формат.",
        )

    try:
        encrypted = value.encode("ascii")
        decrypted = credential_cipher().decrypt(encrypted)
        result = json.loads(decrypted.decode("utf-8"))

    except (
        InvalidToken,
        ValueError,
        TypeError,
        UnicodeError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Не удалось расшифровать CRM-ключи. "
                "Проверьте исходный CRM_ENCRYPTION_KEY."
            ),
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=503,
            detail=(
                "Расшифрованные CRM-ключи имеют неверную структуру."
            ),
        )

    return result


# The Telegram-signed identity may be remembered for seven days using the
# server-signed session cookie. Every request rechecks the numeric allowlist,
# so removing a user from settings revokes an existing session immediately.
CRM_TELEGRAM_SESSION_SECONDS = 7 * 24 * 3600
CRM_VIP_ROUTES = frozenset({
    "/crm/api/session", "/crm/api/dashboard", "/crm/api/finance/calendar",
})


def _crm_role(user_id: int, settings) -> str | None:
    if user_id in settings.admin_telegram_ids:
        return "owner"
    if user_id in settings.crm_vip_telegram_ids:
        return "vip"
    return None


def _crm_session_identity(request: Request, settings) -> dict[str, Any] | None:
    identifier = request.session.get("crm_telegram_id")
    issued = request.session.get("crm_telegram_issued")
    if (
        type(identifier) is not int or identifier <= 0
        or type(issued) is not int or not 0 <= time.time() - issued < CRM_TELEGRAM_SESSION_SECONDS
    ):
        request.session.pop("crm_telegram_id", None)
        request.session.pop("crm_telegram_issued", None)
        return None
    role = _crm_role(identifier, settings)
    if role is None:
        request.session.pop("crm_telegram_id", None)
        request.session.pop("crm_telegram_issued", None)
        return None
    return {
        "id": identifier,
        "actor": f"telegram:{identifier}",
        "first_name": "Владелец" if role == "owner" else "VIP",
        "owner": role == "owner",
    }


def _require_crm_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get("crm_csrf")
    supplied = request.headers.get("x-csrf-token", "")
    if (
        not isinstance(expected, str) or not expected or not supplied
        or not secrets.compare_digest(expected, supplied)
    ):
        raise HTTPException(
            status_code=403, detail="Обновите страницу и повторите действие."
        )


def _enforce_crm_scope(identity: dict[str, Any], request: Request) -> dict[str, Any]:
    if not identity.get("owner"):
        if request.method not in {"GET", "HEAD", "OPTIONS"} or request.url.path not in CRM_VIP_ROUTES:
            raise HTTPException(status_code=403, detail="VIP доступен только обзор CRM.")
    return identity


async def crm_identity(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify Telegram launch once, then reuse a short-lived signed session.

    Full CRM access is restricted to ADMIN_TELEGRAM_IDS or password admins.
    CRM_VIP_TELEGRAM_IDS grants only read-only aggregate overview; commercial
    VIP usernames are never sufficient to access sensitive CRM data.
    """
    settings = get_settings()
    admin_issued = request.session.get("admin_login_at")
    if (
        request.session.get("admin_authenticated") is True
        and type(admin_issued) is int
        and 0 <= time.time() - admin_issued < 8 * 3600
    ):
        _require_crm_csrf(request)
        return {
            "actor": "web:admin", "owner": True, "first_name": "Администратор"
        }

    # Prefer the already-verified session over stale initData, which Telegram
    # may retain after a WebView reopen.
    cached = _crm_session_identity(request, settings)
    if cached is not None:
        _require_crm_csrf(request)
        return _enforce_crm_scope(cached, request)

    if authorization:
        user = current_user(authorization)
        telegram_id = user.get("id")
        if type(telegram_id) is not int or telegram_id <= 0:
            raise HTTPException(status_code=401, detail="Некорректный Telegram ID.")
        role = _crm_role(telegram_id, settings)
        if role is None:
            raise HTTPException(status_code=403, detail="Нет доступа к CRM.")
        identity = {
            **user, "actor": f"telegram:{telegram_id}", "owner": role == "owner"
        }
        identity = _enforce_crm_scope(identity, request)
        # Store a verified numeric Telegram ID, never trust a username.
        # A CRM session is created only after a valid signed /api/session
        # launch. Its cookie signature comes from ADMIN_SESSION_SECRET.
        if request.url.path == "/crm/api/session" and request.method == "GET":
            request.session["crm_telegram_id"] = telegram_id
            request.session["crm_telegram_issued"] = int(time.time())
            request.session["crm_csrf"] = secrets.token_urlsafe(32)
        return identity

    raise HTTPException(
        status_code=401,
        detail="Откройте CRM через кнопку бота Telegram или войдите в /admin/login.",
    )


def require_owner(identity: dict[str, Any]) -> None:
    """Restrict sensitive CRM operations to an authorized owner."""
    if not identity.get("owner"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Управлять доступом и API-ключами "
                "может только администратор."
            ),
        )
