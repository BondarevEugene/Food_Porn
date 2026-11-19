"""Private, deterministic cover-style preview; no child images or AI calls."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.little_legend.illustrated_pdf import EDITION_PALETTES

WIDTH = 720
HEIGHT = 1024
MAX_TITLE = 180


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _lines(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.ImageFont) -> list[str]:
    words = title.split()
    result: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > 550:
            result.append(current)
            current = word
        else:
            current = candidate
    if current:
        result.append(current)
    return result[:5]


def render_palette_preview(*, palette: str, title: str) -> bytes:
    """Generate a 720x1024 PNG showing real palette tokens, not final artwork."""
    if palette not in EDITION_PALETTES:
        raise ValueError("Unknown palette")
    if not title.strip() or len(title) > MAX_TITLE:
        raise ValueError("Invalid book title")
    background, accent, secondary, ink, ornament = EDITION_PALETTES[palette]
    image = Image.new("RGB", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((-185, -175, 350, 360), fill=secondary)
    draw.ellipse((455, 55, 905, 505), fill=accent)
    draw.ellipse((-160, 685, 370, 1215), fill=accent)
    draw.ellipse((430, 745, 850, 1165), fill=secondary)
    draw.rounded_rectangle((65, 80, 655, 940), radius=34, outline=ornament, width=5)
    draw.text((360, 145), "LITTLE LEGEND", font=_font(27), fill=ink, anchor="mm")
    draw.line((235, 195, 485, 195), fill=ornament, width=4)
    draw.ellipse((260, 255, 460, 455), fill=secondary, outline=ornament, width=5)
    draw.ellipse((316, 309, 404, 397), fill=accent)
    font = _font(49)
    lines = _lines(draw, title.strip(), font)
    if len(lines) == 5 and " ".join(lines) != " ".join(title.split()):
        font = _font(34)
        lines = _lines(draw, title.strip(), font)
    line_height = 70 if len(lines) <= 3 else 53
    y = 540 - (len(lines) - 1) * line_height // 2
    for line in lines:
        draw.text((360, y), line, font=font, fill=ink, anchor="mm")
        y += line_height
    draw.text((360, 805), "A PERSONALIZED STORY", font=_font(22),
              fill=ink, anchor="mm")
    draw.text((360, 876), "COLOR STYLE PREVIEW", font=_font(16),
              fill=ink, anchor="mm")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
