"""Ensure completed collages expose the video-story entry action."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "app/bot/handlers/wallpaper.py").read_text(encoding="utf-8")


def test_vip_delivery_always_shows_video_action():
    start = SOURCE.index("    if free_access:", SOURCE.index("async def generate_wallpapers("))
    end = SOURCE.index("    try:\n        ai_cost =", start)
    block = SOURCE[start:end]
    assert 'callback_data="gift_video_plans"' in block
    assert "if settings.miniapp_url:" not in block


def test_paid_checkout_shows_video_action_after_payment_explanation():
    start = SOURCE.index("    if buttons is None:", SOURCE.index("async def generate_wallpapers("))
    end = SOURCE.index('@router.callback_query(F.data.startswith("check_pay_"))', start)
    block = SOURCE[start:end]
    assert 'callback_data="gift_video_plans"' in block
    assert "После подтверждения оплаты" in block


def test_video_entry_requires_scene_studio_configuration():
    start = SOURCE.index("async def send_video_story_entry(")
    end = SOURCE.index('@router.callback_query(F.data == "gift_video_plans")', start)
    block = SOURCE[start:end]
    assert "if not settings.miniapp_url:" in block
    assert "video_story_entry_keyboard(settings, lang)" in block
