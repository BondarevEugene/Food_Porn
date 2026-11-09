"""Guard Telegram entry into the paid Mini App video story flow.

The collage renderer archives photos and removes the temporary upload copies.
Therefore video entry must never rely on upload_paths().
"""
from pathlib import Path

HANDLER = (Path(__file__).resolve().parents[1] / "app/bot/handlers/wallpaper.py").read_text(encoding="utf-8")
API = (Path(__file__).resolve().parents[1] / "app/miniapp/api.py").read_text(encoding="utf-8")


def test_video_buttons_open_scene_studio_without_requiring_temporary_uploads():
    start = HANDLER.index("async def send_video_story_entry(")
    end = HANDLER.index('@router.callback_query(F.data.in_({"gift_safety_one_photo"', start)
    entry = HANDLER[start:end]
    assert "upload_paths(" not in entry
    assert "settings.miniapp_url" in entry
    assert "video_story_entry_keyboard(settings, lang)" in entry
    assert "await send_video_story_entry(callback, state, settings)" in entry


def test_legacy_video_tier_buttons_do_not_promise_unavailable_tiers():
    start = HANDLER.index("async def choose_gift_video_tier(")
    end = HANDLER.index('@router.callback_query(F.data.in_({"gift_safety_one_photo"', start)
    legacy = HANDLER[start:end]
    assert "VideoTier(" in legacy
    assert "await send_video_story_entry(callback, state, settings)" in legacy
    assert "після підключення відеосервісу" not in legacy


def test_video_payment_and_render_remain_in_miniapp():
    assert '@router.post("/api/wallpapers/{order_id}/video-story/orders")' in API
    assert '@router.post("/api/wallpapers/{order_id}/video")' in API
    assert 'if not wallpaper.paid:' in API
    assert 'if video_order is None:' in API
