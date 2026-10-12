"""One permission rule for Telegram buttons, Mini App and CRM endpoints."""

from __future__ import annotations

import logging

from app.config import Settings
from app.services.settings_service import get_vip_users

logger = logging.getLogger(__name__)


async def has_admin_access(
    user_id: int, username: str | None, settings: Settings, session_factory
) -> bool:
    if user_id in settings.admin_telegram_ids:
        return True
    candidate = (username or "").strip().lstrip("@").casefold()
    if not candidate:
        return False
    try:
        async with session_factory() as session:
            names = await get_vip_users(session, settings.default_vip_users)
    except Exception:
        logger.exception("Cannot check CRM access for Telegram ID %s", user_id)
        return False
    return candidate in {name.strip().lstrip("@").casefold() for name in names}


def crm_url(settings: Settings) -> str:
    from urllib.parse import urlsplit, urlunsplit

    if not settings.miniapp_url:
        return ""
    parts = urlsplit(settings.miniapp_url)
    if parts.scheme != "https" or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, "/crm", "", ""))
