"""
==========================================================
FOOD_PORN

Module: Omnichannel Messaging Service
Layer: Integration

Responsibilities:
    - Normalize incoming messages from official provider webhooks
    - Deduplicate callbacks and remember channel contacts
    - Reply with a signed browser entry to the shared Mini App
==========================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.database.models import ChannelContact, ChannelEvent
from app.database.session import async_session_maker
from app.miniapp.auth import create_channel_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InboundEvent:
    channel: str
    event_id: str
    sender_id: str
    text: str = ""
    display_name: str = ""
    language: str = "en"
    reply_target: str | None = None


def miniapp_link(settings: Settings, event: InboundEvent) -> str:
    if not settings.miniapp_url:
        raise RuntimeError("MINIAPP_URL is not configured")
    token = create_channel_token(
        event.channel,
        event.sender_id,
        name=event.display_name,
        language=event.language,
    )
    parts = urlsplit(settings.miniapp_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["channel_token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def welcome_text(settings: Settings, event: InboundEvent) -> str:
    link = miniapp_link(settings, event)
    if event.language.startswith("uk"):
        return f"💛 Відкрийте майстерню Food Porn: {link}"
    if event.language.startswith("ru"):
        return f"💛 Откройте мастерскую Food Porn: {link}"
    return f"💛 Open the Food Porn gift studio: {link}"


async def claim_event(event: InboundEvent) -> bool:
    """Return false for a provider retry that was already handled."""
    async with async_session_maker() as session:
        contact = await session.scalar(
            select(ChannelContact).where(
                ChannelContact.channel == event.channel,
                ChannelContact.external_user_id == event.sender_id,
            )
        )
        if contact is None:
            session.add(
                ChannelContact(
                    channel=event.channel,
                    external_user_id=event.sender_id,
                    display_name=event.display_name or None,
                    language=event.language or None,
                    last_seen_at=datetime.now(UTC),
                )
            )
        else:
            contact.last_seen_at = datetime.now(UTC)
            contact.display_name = event.display_name or contact.display_name
            contact.language = event.language or contact.language
        row = ChannelEvent(
            channel=event.channel,
            event_id=event.event_id,
            external_user_id=event.sender_id,
            event_type="message",
        )
        session.add(row)
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def mark_event(event: InboundEvent, *, error: str | None = None) -> None:
    async with async_session_maker() as session:
        row = await session.scalar(
            select(ChannelEvent).where(
                ChannelEvent.channel == event.channel,
                ChannelEvent.event_id == event.event_id,
            )
        )
        if row:
            row.processed = error is None
            row.error_message = error[:1000] if error else None
            await session.commit()


async def send_meta(settings: Settings, event: InboundEvent, text: str) -> None:
    version = settings.meta_graph_api_version
    if event.channel == "whatsapp":
        token = settings.whatsapp_access_token.get_secret_value()
        node = settings.whatsapp_phone_number_id
        payload = {
            "messaging_product": "whatsapp",
            "to": event.sender_id,
            "type": "text",
            "text": {"body": text, "preview_url": True},
        }
    elif event.channel == "instagram":
        token = settings.instagram_access_token.get_secret_value()
        node = settings.instagram_business_account_id
        payload = {"recipient": {"id": event.sender_id}, "message": {"text": text}}
    else:
        token = settings.messenger_page_access_token.get_secret_value()
        node = settings.messenger_page_id or "me"
        payload = {"recipient": {"id": event.sender_id}, "message": {"text": text}}
    if not token or not node:
        raise RuntimeError(f"{event.channel} credentials are not configured")
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        response = await client.post(
            f"https://graph.facebook.com/{version}/{node}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()


async def send_viber(settings: Settings, event: InboundEvent, text: str) -> None:
    token = settings.viber_auth_token.get_secret_value()
    if not token:
        raise RuntimeError("VIBER_AUTH_TOKEN is not configured")
    payload = {
        "receiver": event.sender_id,
        "min_api_version": 1,
        "sender": {"name": settings.viber_bot_name},
        "type": "text",
        "text": text,
    }
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        response = await client.post(
            "https://chatapi.viber.com/pa/send_message",
            headers={"X-Viber-Auth-Token": token},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") != 0:
            raise RuntimeError(f"Viber status {body.get('status')}: {body.get('status_message')}")


async def send_slack(settings: Settings, event: InboundEvent, text: str) -> None:
    token = settings.slack_bot_token.get_secret_value()
    if not token or not event.reply_target:
        raise RuntimeError("Slack credentials or reply channel are missing")
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        response = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": event.reply_target, "text": text, "unfurl_links": False},
        )
        response.raise_for_status()
        if not response.json().get("ok"):
            raise RuntimeError("Slack rejected the message")


async def process_event(settings: Settings, event: InboundEvent) -> None:
    if not await claim_event(event):
        return
    try:
        text = welcome_text(settings, event)
        if event.channel in {"whatsapp", "messenger", "instagram"}:
            await send_meta(settings, event, text)
        elif event.channel == "viber":
            await send_viber(settings, event, text)
        elif event.channel == "slack":
            await send_slack(settings, event, text)
        await mark_event(event)
    except Exception as exc:
        logger.exception("Could not handle %s event %s", event.channel, event.event_id)
        await mark_event(event, error=f"{type(exc).__name__}: {exc}")
