"""Private Telegram-to-CRM one-time sign-in tickets.

No authorization is granted on the basis of a username, a query user ID, or
an unverified Telegram launch. Tickets are random, short-lived, single-use,
and explicitly limited to numeric CRM allowlists.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.crm.models import CRMLoginTicket
from app.services.admin_access import crm_url

TICKET_TTL = timedelta(minutes=2)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _authorized(user_id: int) -> bool:
    settings = get_settings()
    return user_id in settings.admin_telegram_ids or user_id in settings.crm_vip_telegram_ids


async def issue_crm_login_url(
    factory: async_sessionmaker[AsyncSession], telegram_user_id: int
) -> str | None:
    """Called only by the bot in a private chat with an allowlisted user."""
    if type(telegram_user_id) is not int or not _authorized(telegram_user_id):
        return None
    base_url = crm_url(get_settings())
    if not base_url:
        return None
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(
            CRMLoginTicket(
                token_hash=_digest(token), telegram_user_id=telegram_user_id,
                expires_at=now + TICKET_TTL,
            )
        )
        await session.commit()
    return f"{base_url}/entry/{quote(token, safe='')}"


async def consume_crm_login_ticket(
    factory: async_sessionmaker[AsyncSession], token: str
) -> int | None:
    """Atomic claim: one HTTP request wins even with parallel Railway replicas."""
    if not isinstance(token, str) or not 30 <= len(token) <= 128:
        return None
    try:
        hash_value = _digest(token)
    except UnicodeEncodeError:
        return None
    now = datetime.now(UTC)
    async with factory() as session:
        result = await session.execute(
            update(CRMLoginTicket)
            .where(
                CRMLoginTicket.token_hash == hash_value,
                CRMLoginTicket.used_at.is_(None),
                CRMLoginTicket.expires_at > now,
            )
            .values(used_at=now)
            .returning(CRMLoginTicket.telegram_user_id)
        )
        telegram_id = result.scalar_one_or_none()
        if telegram_id is None or not _authorized(telegram_id):
            await session.rollback()
            return None
        await session.commit()
        return telegram_id
