"""Provider-independent, fail-closed PDF delivery state transitions.

Persist the returned state atomically before sending a Telegram document.
This module deliberately performs no network calls or database writes.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DeliveryStatus(StrEnum):
    READY = "ready"
    SENDING = "sending"
    SENT = "sent"
    UNCERTAIN = "uncertain"


class BookDelivery(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: DeliveryStatus = DeliveryStatus.READY
    attempt_id: str | None = None
    dispatched_at: datetime | None = None
    sent_at: datetime | None = None
    telegram_message_id: int | None = None


def begin_delivery(delivery: BookDelivery, *, attempt_id: str) -> BookDelivery:
    """Reserve a single attempt; retries need explicit reconciliation."""
    if delivery.status != DeliveryStatus.READY:
        raise PermissionError("Delivery is already started or completed")
    if not attempt_id.strip() or len(attempt_id) > 120:
        raise ValueError("Valid attempt ID is required")
    return delivery.model_copy(update={
        "status": DeliveryStatus.SENDING, "attempt_id": attempt_id,
        "dispatched_at": datetime.now(UTC),
    })


def confirm_delivery(
    delivery: BookDelivery, *, attempt_id: str, message_id: int,
) -> BookDelivery:
    """Accept only the acknowledgement for the active attempt."""
    if (delivery.status != DeliveryStatus.SENDING
            or delivery.attempt_id != attempt_id or message_id <= 0):
        raise PermissionError("Delivery acknowledgement does not match")
    return delivery.model_copy(update={
        "status": DeliveryStatus.SENT,
        "sent_at": datetime.now(UTC),
        "telegram_message_id": message_id,
    })


def mark_uncertain(delivery: BookDelivery, *, attempt_id: str) -> BookDelivery:
    """Network timeout may mean Telegram accepted the PDF: never auto-resend."""
    if (delivery.status != DeliveryStatus.SENDING
            or delivery.attempt_id != attempt_id):
        raise PermissionError("Delivery attempt does not match")
    return delivery.model_copy(update={"status": DeliveryStatus.UNCERTAIN})
