
"""Telegram authorization, browser sessions and encrypted CRM credentials."""

from __future__ import annotations

import json
import secrets
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


async def crm_identity(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """
    Resolve the authenticated CRM identity.

    Telegram authorization:
        Only IDs listed in ADMIN_TELEGRAM_IDS are allowed.

    Browser authorization:
        Requires an authenticated admin session.
        Every state-changing request must contain a valid CSRF token.
    """
    settings = get_settings()

    # Browser admin session authorization.
    if request.session.get("admin_authenticated") is True:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            expected = request.session.get("crm_csrf")
            supplied = request.headers.get("x-csrf-token", "")

            if (
                not isinstance(expected, str)
                or not expected
                or not supplied
                or not secrets.compare_digest(expected, supplied)
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Обновите страницу и повторите действие.",
                )

        return {
            "actor": "web:admin",
            "owner": True,
            "first_name": "Администратор",
        }


    # Telegram Mini App authorization.
    if authorization:
        user = current_user(authorization)
        telegram_id = user.get("id")

        if (
            not isinstance(telegram_id, int)
            or isinstance(telegram_id, bool)
            or telegram_id <= 0
        ):
            raise HTTPException(
                status_code=401,
                detail="Некорректный Telegram ID.",
            )

        # CRM access is granted only by an explicit Telegram ID.
        # Usernames and VIP usernames are not authorization credentials.
        if telegram_id not in settings.admin_telegram_ids:
            raise HTTPException(
                status_code=403,
                detail="Нет доступа к CRM.",
            )

        return {
            **user,
            "actor": f"telegram:{telegram_id}",
            "owner": True,
        }

    raise HTTPException(
        status_code=401,
        detail=(
            "Откройте CRM из Telegram "
            "или войдите через /admin/login."
        ),
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
