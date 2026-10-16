"""
==========================================================
FOOD_PORN

Module: Messenger Webhook Router
Layer: HTTP Integration

Official adapters: WhatsApp Cloud API, Facebook Messenger, Instagram
Messaging, Viber Bot API, Slack Events API and Discord Interactions.
==========================================================
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.channels.service import InboundEvent, process_event, welcome_text
from app.config import get_settings

router = APIRouter(prefix="/channels", tags=["Messaging Channels"])


def _check_hmac(secret: str, payload: bytes, supplied: str, *, prefix: str = "") -> None:
    if not secret:
        raise HTTPException(503, "Channel secret is not configured")
    expected = prefix + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid webhook signature")


@router.get("/health")
async def channel_health() -> dict:
    settings = get_settings()
    return {
        "telegram": True,
        "whatsapp": bool(settings.whatsapp_access_token.get_secret_value() and settings.whatsapp_phone_number_id),
        "messenger": bool(settings.messenger_page_access_token.get_secret_value()),
        "instagram": bool(settings.instagram_access_token.get_secret_value()),
        "viber": bool(settings.viber_auth_token.get_secret_value()),
        "slack": bool(settings.slack_signing_secret.get_secret_value() and settings.slack_bot_token.get_secret_value()),
        "discord": bool(settings.discord_public_key),
    }


@router.get("/meta/webhook")
async def verify_meta(request: Request) -> PlainTextResponse:
    settings = get_settings()
    query = request.query_params
    if (
        query.get("hub.mode") == "subscribe"
        and query.get("hub.verify_token") == settings.meta_verify_token.get_secret_value()
        and query.get("hub.challenge")
    ):
        return PlainTextResponse(query["hub.challenge"])
    raise HTTPException(403, "Meta webhook verification failed")


def _meta_events(payload: dict[str, Any]) -> list[InboundEvent]:
    events: list[InboundEvent] = []
    if payload.get("object") == "whatsapp_business_account":
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                names = {
                    str(item.get("wa_id")): str((item.get("profile") or {}).get("name") or "")
                    for item in value.get("contacts") or []
                }
                for message in value.get("messages") or []:
                    sender = str(message.get("from") or "")
                    if sender and message.get("id"):
                        events.append(
                            InboundEvent(
                                "whatsapp",
                                str(message["id"]),
                                sender,
                                str((message.get("text") or {}).get("body") or ""),
                                names.get(sender, ""),
                            )
                        )
        return events
    channel = "instagram" if payload.get("object") == "instagram" else "messenger"
    for entry in payload.get("entry") or []:
        for message in entry.get("messaging") or []:
            body = message.get("message") or {}
            sender = str((message.get("sender") or {}).get("id") or "")
            event_id = str(body.get("mid") or message.get("timestamp") or "")
            if sender and event_id and not body.get("is_echo"):
                events.append(InboundEvent(channel, event_id, sender, str(body.get("text") or "")))
    return events


@router.post("/meta/webhook")
async def meta_webhook(request: Request, background: BackgroundTasks) -> dict:
    settings = get_settings()
    raw = await request.body()
    _check_hmac(
        settings.meta_app_secret.get_secret_value(),
        raw,
        request.headers.get("X-Hub-Signature-256", ""),
        prefix="sha256=",
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    events = _meta_events(payload)
    for event in events:
        background.add_task(process_event, settings, event)
    return {"received": len(events)}


@router.post("/viber/webhook")
async def viber_webhook(request: Request, background: BackgroundTasks) -> dict:
    settings = get_settings()
    raw = await request.body()
    _check_hmac(
        settings.viber_auth_token.get_secret_value(),
        raw,
        request.headers.get("X-Viber-Content-Signature", ""),
    )
    payload = json.loads(raw)
    event_type = payload.get("event")
    sender = payload.get("sender") or payload.get("user") or {}
    sender_id = str(sender.get("id") or "")
    if event_type in {"message", "conversation_started"} and sender_id:
        message = payload.get("message") or {}
        event = InboundEvent(
            "viber",
            str(payload.get("message_token") or payload.get("timestamp")),
            sender_id,
            str(message.get("text") or ""),
            str(sender.get("name") or ""),
            str(sender.get("language") or "en"),
        )
        background.add_task(process_event, settings, event)
        return {"received": 1}
    return {"received": 0}


@router.post("/slack/events")
async def slack_events(request: Request, background: BackgroundTasks) -> dict:
    settings = get_settings()
    raw = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(401, "Expired Slack webhook") from exc
    base = b"v0:" + timestamp.encode() + b":" + raw
    _check_hmac(
        settings.slack_signing_secret.get_secret_value(),
        base,
        request.headers.get("X-Slack-Signature", ""),
        prefix="v0=",
    )
    payload = json.loads(raw)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    item = payload.get("event") or {}
    if item.get("type") == "message" and item.get("user") and not item.get("bot_id"):
        event = InboundEvent(
            "slack",
            str(payload.get("event_id")),
            str(item["user"]),
            str(item.get("text") or ""),
            reply_target=str(item.get("channel") or ""),
        )
        background.add_task(process_event, settings, event)
        return {"received": 1}
    return {"received": 0}


@router.post("/discord/interactions")
async def discord_interactions(request: Request, background: BackgroundTasks) -> dict:
    settings = get_settings()
    raw = await request.body()
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(settings.discord_public_key))
        key.verify(
            bytes.fromhex(request.headers.get("X-Signature-Ed25519", "")),
            request.headers.get("X-Signature-Timestamp", "").encode() + raw,
        )
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(401, "Invalid Discord signature") from exc
    payload = json.loads(raw)
    if payload.get("type") == 1:
        return {"type": 1}
    identity = (payload.get("member") or {}).get("user") or payload.get("user") or {}
    sender = str(identity.get("id") or "")
    if not sender:
        raise HTTPException(400, "Discord user missing")
    event = InboundEvent(
        "discord",
        str(payload.get("id")),
        sender,
        display_name=str(identity.get("global_name") or identity.get("username") or ""),
    )
    background.add_task(process_event, settings, event)
    return {"type": 4, "data": {"content": welcome_text(settings, event), "flags": 64}}
