"""Scene direction is deterministic, varied, and respects the meal/mood brief."""
import pytest

from app.services.menu_living_scene import plan_living_scene


@pytest.mark.parametrize("meal,theme", [
    ("breakfast", "light"),
    ("lunch", "color"),
    ("dinner", "dark"),
])
@pytest.mark.parametrize("mood", ["family", "romantic", "sensual", "festive", "playful"])
def test_scene_matrix(meal, theme, mood):
    scene = plan_living_scene(meal=meal, mood=mood, order_seed=123)
    assert scene.visual_theme == theme
    assert scene.cover_action != scene.spread_action
    assert "Photorealistic" in scene.scene_prompt(page="cover")
    assert "pasted-on" in scene.scene_prompt(page="spread")
    assert scene.art_direction.startswith(theme + "-")


def test_reproducible_and_diverse():
    a = plan_living_scene(meal="breakfast", mood="family", order_seed="order-7")
    assert a == plan_living_scene(meal="breakfast", mood="family", order_seed="order-7")
    variants = {
        (
            s.setting, s.cover_action, s.props, s.paper, s.typography,
            s.ornament, s.art_direction,
        )
        for n in range(30)
        for s in [plan_living_scene(meal="breakfast", mood="family", order_seed=n)]
    }
    assert len(variants) >= 20


@pytest.mark.parametrize("kwargs", [
    {"meal": "snack", "mood": "family"},
    {"meal": "dinner", "mood": "unknown"},
])
def test_invalid_choices_fail(kwargs):
    with pytest.raises(ValueError):
        plan_living_scene(**kwargs, order_seed=1)


def test_invalid_page_fails():
    scene = plan_living_scene(meal="dinner", mood="festive", order_seed=1)
    with pytest.raises(ValueError):
        scene.scene_prompt(page="other")
