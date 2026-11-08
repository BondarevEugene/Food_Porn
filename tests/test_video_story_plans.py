"""Video-story tier contracts: no accidental cross-tier entitlements."""
import pytest

from app.services.video_story_plans import VIDEO_PLANS, VideoTier, get_video_plan, video_plan_label


@pytest.mark.parametrize("tier", list(VideoTier))
def test_video_tiers_have_distinct_duration_and_entitlements(tier):
    plan = get_video_plan(tier)
    assert plan.seconds > 0
    assert plan.soundtrack is True
    assert plan.animated_photos is True


def test_premium_has_narration_and_ai_motion():
    assert VIDEO_PLANS[VideoTier.PREMIUM].narration
    assert VIDEO_PLANS[VideoTier.PREMIUM].ai_motion_scenes
    assert not VIDEO_PLANS[VideoTier.ECONOMY].ai_motion_scenes
    assert not VIDEO_PLANS[VideoTier.CINEMATIC].narration


def test_invalid_tier_is_rejected():
    with pytest.raises(ValueError):
        get_video_plan("free_unlimited")


@pytest.mark.parametrize("language", ["uk", "ru", "en"])
def test_all_tiers_have_labels(language):
    assert all(video_plan_label(tier, language) for tier in VideoTier)
