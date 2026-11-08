"""Pricing contracts for three independently managed video-story tariffs."""
from decimal import Decimal

import pytest

from app.services.video_story_plans import VideoTier, make_video_price


@pytest.mark.parametrize("tier", list(VideoTier))
def test_each_tier_can_have_independent_price(tier):
    price = make_video_price(tier, "199.00")
    assert price.tier == tier
    assert price.amount == Decimal("199.00")
    assert price.currency == "UAH"


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "1.001"])
def test_invalid_price_is_rejected(amount):
    with pytest.raises(ValueError):
        make_video_price("economy", amount)


def test_tariff_can_be_disabled():
    assert make_video_price("premium", "999.00", enabled=False).enabled is False
