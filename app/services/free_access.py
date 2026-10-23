"""One consistent rule for authorized generation without a payment invoice."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.settings_service import get_paid_test_user_ids, get_vip_users

logger = logging.getLogger(__name__)


async def has_free_generation_access(
    user_id: int, username: str | None, settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """Check owner/VIP access with an explicit commercial-test override."""
    if user_id in settings.admin_telegram_ids:
        try:
            async with session_factory() as session:
                if user_id in await get_paid_test_user_ids(session):
                    return False
        except Exception:
            logger.exception("Could not check paid test mode for owner %s", user_id)
        return True
    if user_id in settings.free_generation_telegram_ids:
        return True
    candidate = (username or "").strip().lstrip("@").casefold()
    if not candidate:
        return False
    try:
        async with session_factory() as session:
            vip_users = await get_vip_users(session, settings.default_vip_users)
    except Exception:
        logger.exception("Could not check VIP usernames for user %s", user_id)
        return False
    return candidate in {name.strip().lstrip("@").casefold() for name in vip_users}
