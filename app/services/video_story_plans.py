"""Video-story product tiers. Pricing is deliberately not activated until checkout is wired."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class VideoTier(StrEnum):
    ECONOMY = "economy"
    CINEMATIC = "cinematic"
    PREMIUM = "premium"


@dataclass(frozen=True, slots=True)
class VideoPlan:
    tier: VideoTier
    seconds: int
    animated_photos: bool
    ai_motion_scenes: bool
    narration: bool
    soundtrack: bool
    advanced_editing: bool


VIDEO_PLANS: dict[VideoTier, VideoPlan] = {
    VideoTier.ECONOMY: VideoPlan(VideoTier.ECONOMY, 15, True, False, False, True, False),
    VideoTier.CINEMATIC: VideoPlan(VideoTier.CINEMATIC, 30, True, True, False, True, True),
    VideoTier.PREMIUM: VideoPlan(VideoTier.PREMIUM, 60, True, True, True, True, True),
}


def get_video_plan(value: str | VideoTier) -> VideoPlan:
    """Validate a client-supplied tier; never silently upgrade a paid order."""
    return VIDEO_PLANS[VideoTier(value)]


def video_plan_label(tier: VideoTier, language: str = "uk") -> str:
    labels = {
        VideoTier.ECONOMY: ("Економ", "Эконом", "Economy"),
        VideoTier.CINEMATIC: ("Кінематографічний", "Кинематографический", "Cinematic"),
        VideoTier.PREMIUM: ("Преміум", "Премиум", "Premium"),
    }
    return labels[tier][{"uk": 0, "ru": 1, "en": 2}.get(language, 0)]


@dataclass(frozen=True, slots=True)
class VideoPrice:
    """An administrator-controlled tariff price; never derive a payment from UI text."""
    tier: VideoTier
    amount: Decimal
    currency: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount <= 0 or self.amount.as_tuple().exponent < -2:
            raise ValueError("Video price must be a positive amount with at most two decimal places")
        if self.currency not in {"UAH", "USD", "EUR"}:
            raise ValueError("Unsupported video price currency")


def make_video_price(tier: str | VideoTier, amount: Decimal | str, currency: str = "UAH",
                     enabled: bool = True) -> VideoPrice:
    """Validate prices at the boundary before persisting them in the tariff catalog."""
    return VideoPrice(VideoTier(tier), Decimal(str(amount)), currency, enabled)
