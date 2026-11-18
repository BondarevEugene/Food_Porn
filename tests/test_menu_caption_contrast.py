"""Regression checks for printable menu legibility and portrait panel."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.render.booklet import BookletRenderer


def test_caption_uses_dark_text_on_light_and_color(monkeypatch, tmp_path):
    renderer = BookletRenderer(tmp_path)
    observed = []
    monkeypatch.setattr(renderer, "_safe_item_image", lambda path, width, height: Image.new("RGB", (width, height), "red"))
    monkeypatch.setattr(renderer, "_fit_card_title", lambda *args, **kwargs: observed.append(kwargs))
    renderer._px = lambda value: max(1, round(value))
    item = SimpleNamespace(title="Beautiful lunch", image_path=Path("unused"))
    for style in ("light", "color", "dark"):
        renderer.style = style
        renderer.PANEL = (250, 245, 230) if style != "dark" else (20, 20, 20)
        renderer.MUTED = (110, 110, 110)
        renderer.GOLD = (150, 110, 60)
        page = Image.new("RGB", (400, 400), "white")
        renderer._draw_item_card(page, (10, 10, 300, 250), item, None, compact=True)
    assert observed[0]["text_color"] == (24, 25, 26)
    assert observed[1]["text_color"] == (24, 25, 26)
    assert observed[2]["text_color"] == (249, 243, 232)
