"""Regression checks for Little Legend third-product integration."""
import pytest
from pydantic import ValidationError

from app.little_legend.router import DEFAULT_SCENES, StoryDraft
from app.bot.handlers.start import get_products_menu_keyboard


def test_little_legend_is_third_product_before_service_actions():
    keyboard = get_products_menu_keyboard(user_id=123456789, lang="ru")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks[:3] == ["prod_food_porn", "prod_manifestation", "prod_little_legend"]
    assert callbacks.index("prod_little_legend") < callbacks.index("home_orders")


def test_story_draft_defaults_to_twelve_editable_scenes():
    draft = StoryDraft()
    assert len(draft.scenes) == 12
    assert draft.scenes == DEFAULT_SCENES
    assert draft.hero == "Оля"


def test_story_draft_rejects_unbounded_input():
    with pytest.raises(ValidationError):
        StoryDraft(hero="A" * 101)
    with pytest.raises(ValidationError):
        StoryDraft(scenes=["x"] * 41)


def test_studio_does_not_embed_secrets_or_unsafe_html():
    from app.little_legend.router import STUDIO_HTML
    assert "Telegram.WebApp" in STUDIO_HTML
    assert "textContent" in STUDIO_HTML
    assert "innerHTML" not in STUDIO_HTML
    assert "Authorization:'tma '" in STUDIO_HTML
