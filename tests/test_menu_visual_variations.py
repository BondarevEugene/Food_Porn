from types import SimpleNamespace

from app.services.menu_art_directions import choose_direction
from app.services.menu_romance_copy import romantic_copy


def test_romantic_copy_reproducible_and_localized():
    for lang in ("ru", "uk", "en"):
        quote, greeting = romantic_copy(lang, "order-42")
        assert (quote, greeting) == romantic_copy(lang, "order-42")
        assert quote and greeting
        assert "— " not in quote


def test_direction_palette_and_layout_variants(tmp_path):
    from app.render.booklet import BookletRenderer

    renderer = BookletRenderer(tmp_path)
    signatures = set()
    for theme in ("light", "dark", "color"):
        for index in range(1, 16 if theme != "color" else 21):
            preset = f"{theme}-{index:02d}"
            renderer._apply_style(SimpleNamespace(
                visual_style=theme,
                design_seed=42,
                design_preset=preset,
                id=42,
            ))
            signatures.add((renderer.BG, renderer.GOLD, renderer.layout_variant))
            assert renderer.direction.code == preset
    assert len(signatures) == 50


def test_random_direction_is_repeatable():
    assert choose_direction("color", "restaurant-edition-featured-v1") == choose_direction(
        "color", "restaurant-edition-featured-v1"
    )
