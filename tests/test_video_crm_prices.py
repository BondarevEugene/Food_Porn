"""CRM persistence and validation contracts for video story tariffs."""
from decimal import Decimal

import pytest

from app.crm.service import SETTING_RULES, validate_settings


@pytest.mark.parametrize("tier", ["economy", "cinematic", "premium"])
def test_video_tier_is_editable_in_crm(tier):
    key = f"video_{tier}_price_uah"
    assert key in SETTING_RULES
    assert validate_settings({key: "249.50"})[key] == "249.50"


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "100000.01"])
def test_video_price_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_settings({"video_economy_price_uah": value})


def test_independent_video_prices_do_not_overwrite_other_tiers():
    result = validate_settings({
        "video_economy_price_uah": Decimal("199"),
        "video_cinematic_price_uah": Decimal("499"),
        "video_premium_price_uah": Decimal("999"),
    })
    assert result == {
        "video_economy_price_uah": "199.00",
        "video_cinematic_price_uah": "499.00",
        "video_premium_price_uah": "999.00",
    }


def test_runtime_video_uah_tariff_preserves_decimal(monkeypatch):
    from app.crm import service

    class RuntimeSettings:
        wayforpay_video_story_price_uah = None
        video_story_price_stars = 0

    settings = RuntimeSettings()
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    service.apply_runtime_values({
        "wayforpay_video_story_price_uah": "249.50",
        "video_story_price_stars": "150",
    })
    assert settings.wayforpay_video_story_price_uah == Decimal("249.50")
    assert isinstance(settings.wayforpay_video_story_price_uah, Decimal)
    assert settings.video_story_price_stars == 150
