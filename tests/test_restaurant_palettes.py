"""Restaurant Edition palette regression checks."""
from pathlib import Path
from types import SimpleNamespace

from app.render.booklet import BookletRenderer


def test_restaurant_palettes_are_distinct(tmp_path: Path):
    renderer = BookletRenderer(tmp_path)
    colors = []
    for style in ("dark", "light", "color"):
        renderer._apply_style(SimpleNamespace(design_style=style))
        colors.append((renderer.BG, renderer.PANEL, renderer.GOLD, renderer.CREAM))
    assert len(set(colors)) == 3
    assert colors[1][0][0] > colors[0][0][0]


def test_unknown_style_falls_back_to_existing_dark_palette(tmp_path: Path):
    renderer = BookletRenderer(tmp_path)
    renderer._apply_style(SimpleNamespace(design_style="unknown"))
    assert (renderer.BG, renderer.GOLD) == ((20, 17, 17), (214, 171, 92))
