"""The product selector must appear only after photo upload is finished."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "app/bot/handlers/wallpaper.py").read_text(encoding="utf-8")


def test_photo_upload_keyboard_has_no_premature_video_offer():
    block = SOURCE.split("def finish_photos_keyboard(", 1)[1].split("def gift_product_keyboard(", 1)[0]
    assert 'callback_data="gift_photos_done"' in block
    assert 'callback_data="gift_video_plans"' not in block


def test_three_product_choices_are_available_after_photos():
    block = SOURCE.split("def gift_product_keyboard(", 1)[1].split("def video_story_entry_keyboard(", 1)[0]
    assert all(f'("{product}",' in block for product in ("collage", "video", "both"))
    assert 'callback_data=f"gift_product:{key}"' in block


def test_product_choice_is_stored_before_collecting_goals():
    block = SOURCE.split("async def select_gift_product(", 1)[1].split(
        '@router.callback_query(F.data == "gift_photos_done")', 1
    )[0]
    assert 'await state.update_data(gift_product=product)' in block
    assert 'await state.set_state(WallpaperStates.waiting_for_goals)' in block
