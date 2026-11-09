"""Контракт окремого платного замовлення відеоісторії.

Модуль не змінює платіжні таблиці та не надає доступу до генерації:
застосування переходів має відбуватися лише після перевіреного webhook.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoOrderStatus(StrEnum):
    WAITING_FOR_PAYMENT = "waiting_for_payment"
    PAID = "paid"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    REFUNDED = "refunded"


_ALLOWED_TRANSITIONS = {
    VideoOrderStatus.WAITING_FOR_PAYMENT: {VideoOrderStatus.PAID},
    VideoOrderStatus.PAID: {VideoOrderStatus.QUEUED, VideoOrderStatus.REFUNDED},
    VideoOrderStatus.QUEUED: {VideoOrderStatus.PROCESSING, VideoOrderStatus.FAILED},
    VideoOrderStatus.PROCESSING: {VideoOrderStatus.READY, VideoOrderStatus.FAILED},
    VideoOrderStatus.FAILED: {VideoOrderStatus.QUEUED, VideoOrderStatus.REFUNDED},
    VideoOrderStatus.READY: {VideoOrderStatus.REFUNDED},
    VideoOrderStatus.REFUNDED: set(),
}


class VideoOrderContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: int = Field(gt=0)
    wallpaper_order_id: int = Field(gt=0)
    owner_telegram_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="UAH", pattern=r"^[A-Z]{3}$")
    status: VideoOrderStatus = VideoOrderStatus.WAITING_FOR_PAYMENT
    payment_reference: str | None = None
    paid_at: datetime | None = None
    music_mode: str = "auto"
    music_mood: str = "cinematic"
    ai_voice: bool = False

    @model_validator(mode="after")
    def validate_payment(self):
        if self.status not in {
            VideoOrderStatus.WAITING_FOR_PAYMENT, VideoOrderStatus.REFUNDED
        } and (not self.payment_reference or self.paid_at is None):
            raise ValueError("Verified payment evidence is required")
        return self

    def transition(self, next_status: VideoOrderStatus) -> "VideoOrderContract":
        if next_status == self.status:
            return self
        if next_status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid video order transition: {self.status} -> {next_status}")
        return self.model_copy(update={"status": next_status})

    def can_download(self, requester_id: int) -> bool:
        return (
            requester_id == self.owner_telegram_id
            and self.status == VideoOrderStatus.READY
            and self.payment_reference is not None
            and self.paid_at is not None
        )
