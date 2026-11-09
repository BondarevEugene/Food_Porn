"""Regression checks for Telegram WebApp launch and explicit album completion."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "app/bot/handlers/wallpaper.py").read_text(encoding="utf-8")


def test_video_entry_uses_telegram_webapp_not_external_url():
    start = SOURCE.index("def video_story_entry_keyboard(")
    end = SOURCE.index("async def send_video_story_entry(", start)
    section = SOURCE[start:end]
    assert "web_app=WebAppInfo(url=settings.miniapp_url)" in section
    assert "url=settings.miniapp_url," not in section.replace(
        "web_app=WebAppInfo(url=settings.miniapp_url)", ""
    )


def test_seventh_photo_does_not_advance_state_without_done():
    start = SOURCE.index("async def collect_five_photos(")
    end = SOURCE.index("@router.message(WallpaperStates.waiting_for_five_photos)", start)
    section = SOURCE[start:end]
    assert "await state.set_state(" not in section
    assert "reply_markup=finish_photos_keyboard(lang)" in section


def test_stale_done_callback_is_answered():
    assert '@router.callback_query(F.data == "gift_photos_done")' in SOURCE
    assert "async def finish_gift_photos_outside_upload(" in SOURCE
    assert "await callback.answer()" in SOURCE.split(
        "async def finish_gift_photos_outside_upload(", 1
    )[1].split("@router.message(", 1)[0]
