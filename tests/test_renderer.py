"""
==========================================================
FOOD_PORN

Module: Booklet Renderer Tests
Layer: Test

Responsibilities:
    - Verify preview and PDF creation
    - Verify the spread photograph reaches print edges
==========================================================
"""

from pathlib import Path

from PIL import Image

from app.database.models import Customer, GenerationStatus, ItemCategory, Menu, MenuItem
from app.render.booklet import BookletRenderer


def sample_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (500, 700), color).save(path, "JPEG")


def test_renderer_creates_two_previews_and_pdf(tmp_path) -> None:
    cover = tmp_path / "cover.jpg"
    spread = tmp_path / "spread.jpg"
    food = tmp_path / "food.jpg"
    sample_image(cover, (90, 30, 20))
    sample_image(spread, (30, 30, 60))
    sample_image(food, (120, 80, 30))

    customer = Customer(
        telegram_user_id=123,
        phone="+380000000000",
        name="Test",
        country="Ukraine",
        city="Kyiv",
    )
    menu = Menu(
        id=1,
        customer=customer,
        customer_id=1,
        cover_photo_path=str(cover),
        spread_photo_path=str(spread),
    )
    menu.items = []
    position = 0
    for category, count in (
        (ItemCategory.MAIN, 3),
        (ItemCategory.APPETIZER, 3),
        (ItemCategory.DESSERT, 3),
        (ItemCategory.DRINK, 3),
    ):
        for index in range(1, count + 1):
            position += 1
            menu.items.append(
                MenuItem(
                    id=position,
                    menu_id=1,
                    category=category,
                    position=index,
                    title=f"Item {position}",
                    image_path=str(food),
                    generation_status=GenerationStatus.DONE,
                )
            )

    original_dpi = BookletRenderer.DPI
    BookletRenderer.DPI = 72
    try:
        result = BookletRenderer(tmp_path / "out").render(menu)
    finally:
        BookletRenderer.DPI = original_dpi
    assert result.outside_preview.stat().st_size > 1000
    assert result.inside_preview.stat().st_size > 1000
    assert result.print_pdf.read_bytes().startswith(b"%PDF")

    # The spread photo reaches the right and bottom trim edges instead of
    # being rendered as a narrow, rounded photo card.
    with Image.open(result.inside_preview) as preview:
        right_bottom = preview.getpixel((preview.width - 25, preview.height - 25))
        assert right_bottom[2] > right_bottom[0]
