"""Every palette produces a private PNG cover-style preview."""
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.little_legend.illustrated_pdf import EDITION_PALETTES
from app.little_legend.palette_preview import (
    HEIGHT,
    WIDTH,
    _title_layout,
    render_palette_preview,
)


@pytest.mark.parametrize("palette", sorted(EDITION_PALETTES))
def test_palette_preview_png_for_all_fifteen_colors(palette: str) -> None:
    data = render_palette_preview(palette=palette, title="Марта и звёздный сад")
    assert data[:8] == bytes((137, 80, 78, 71, 13, 10, 26, 10))
    assert len(data) < 2_000_000
    with Image.open(BytesIO(data)) as image:
        assert image.size == (WIDTH, HEIGHT)
        assert image.mode == "RGB"
        assert image.getpixel((0, 500)) == tuple(
            bytes.fromhex(EDITION_PALETTES[palette][0].lstrip("#"))
        )


@pytest.mark.parametrize("palette,title", [
    ("invalid", "Марта"),
    ("lavender", ""),
    ("lavender", "x" * 181),
])
def test_palette_preview_rejects_invalid_input(palette: str, title: str) -> None:
    with pytest.raises(ValueError):
        render_palette_preview(palette=palette, title=title)


def test_palette_preview_is_deterministic() -> None:
    first = render_palette_preview(palette="forest", title="Сказочный лес")
    second = render_palette_preview(palette="forest", title="Сказочный лес")
    assert first == second


@pytest.mark.parametrize("title", [
    "Супердлинноесловобезпробелов" * 5,
    "Марта и её невероятные приключения в волшебном лесу " * 3,
    "A" * 180,
    "М" * 180,
])
def test_long_titles_are_not_silently_truncated(title: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    font, lines, line_height = _title_layout(ImageDraw.Draw(image), title)
    assert "".join(lines).replace(" ", "") == title.replace(" ", "")
    assert len(lines) * line_height <= 245
    draw = ImageDraw.Draw(image)
    assert all(draw.textbbox((0, 0), line, font=font)[2] <= 540
               for line in lines)
    data = render_palette_preview(palette="lavender", title=title)
    with Image.open(BytesIO(data)) as preview:
        assert preview.size == (WIDTH, HEIGHT)
