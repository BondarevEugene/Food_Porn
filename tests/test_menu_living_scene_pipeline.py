"""Living-scene production wiring: same brief drives food prompts and print."""
from types import SimpleNamespace

import pytest

from app.database.models import ItemCategory
from app.render.booklet import menu_render_snapshot
from app.services.menu_living_scene import plan_living_scene
from app.services.prompt_builder import PromptBuilder


@pytest.mark.parametrize("meal,theme", [
    ("breakfast", "light"),
    ("lunch", "color"),
    ("dinner", "dark"),
])
def test_scene_drives_dish_and_print(meal, theme):
    scene = plan_living_scene(meal=meal, mood="romantic", order_seed=42)
    item = SimpleNamespace(title="Омлет с грибами", category=ItemCategory.MAIN)
    prompt = PromptBuilder().build(item, scene=scene)
    assert scene.setting in prompt
    assert scene.lighting in prompt
    assert scene.art_direction in prompt
    assert "No people" in prompt
    menu = SimpleNamespace(
        id=42, meal_period=meal, design_seed=42, design_preset=None,
        visual_style="premium_dark", cover_photo_path="cover.jpg",
        spread_photo_path="spread.jpg",
        customer=SimpleNamespace(name="Test", language="ru"), items=[],
    )
    snapshot = menu_render_snapshot(menu)
    assert snapshot.visual_style == theme
    assert snapshot.design_preset == scene.art_direction


def test_legacy_full_day_preserves_style_and_prompt():
    item = SimpleNamespace(title="Суп", category=ItemCategory.SOUP)
    assert "dark matte charcoal background" in PromptBuilder().build(item)
    menu = SimpleNamespace(
        id=42, meal_period="full_day", design_seed=42, design_preset=None,
        visual_style="dark", cover_photo_path="cover.jpg",
        spread_photo_path="spread.jpg",
        customer=SimpleNamespace(name="Test", language="ru"), items=[],
    )
    assert menu_render_snapshot(menu).visual_style == "dark"
