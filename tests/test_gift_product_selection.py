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


def test_product_selection_is_a_distinct_fsm_step():
    states = (Path(__file__).resolve().parents[1] / "app/bot/states/wallpaper.py").read_text(
        encoding="utf-8"
    )
    finish = SOURCE.split("async def finish_gift_photos(", 1)[1].split(
        '@router.callback_query(F.data.startswith("gift_product:"))', 1
    )[0]
    select = SOURCE.split("async def select_gift_product(", 1)[1].split(
        '@router.callback_query(F.data == "gift_photos_done")', 1
    )[0]
    assert "waiting_for_product = State()" in states
    assert "await state.set_state(WallpaperStates.waiting_for_product)" in finish
    assert "WallpaperStates.waiting_for_product.state" in select


def test_video_selection_cannot_enter_collage_only_checkout():
    goals = SOURCE.split("async def collect_goals(", 1)[1].split(
        '@router.message(WallpaperStates.waiting_for_goals)', 1
    )[0]
    generation = SOURCE.split("async def generate_wallpapers(", 1)[1].split(
        '@router.callback_query(F.data.startswith("check_pay_"))', 1
    )[0]
    assert 'data.get("gift_product") in {"video", "both"}' in goals
    assert 'data.get("gift_product") in {"video", "both"}' in generation
    assert "raise RuntimeError" in generation
