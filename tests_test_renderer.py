"""
==========================================================
FOOD_PORN

Module: Booklet Renderer Tests (Professional Edition)
Layer: Test

Responsibilities:
    - Verify preview and PDF creation
    - Verify spread photograph and giver's photo integration
    - Verify item counts and error handling for missing assets
==========================================================
"""

from pathlib import Path

import pytest
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
        name="Eugene",
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
        (ItemCategory.MAIN, 2),
        (ItemCategory.APPETIZER, 2),
        (ItemCategory.DESSERT, 2),
        (ItemCategory.DRINK, 2),
    ):
        for index in range(1, count + 1):
            position += 1
            menu.items.append(
                MenuItem(
                    id=position,
                    menu_id=1,
                    category=category,
                    position=index,
                    title=f"Dish {position}",
                    image_path=str(food),
                    generation_status=GenerationStatus.DONE,
                    romantic_price="Поцелуй искренний и сладкий",
                    drink_pairing="Merlot Reserve",
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


def test_missing_food_photo_cannot_be_published(tmp_path) -> None:
    photo = tmp_path / "cover.jpg"
    sample_image(photo, (92, 80, 63))
    customer = Customer(telegram_user_id=123, phone="+380000000000", name="Test", country="Ukraine", city="Kyiv")
    menu = Menu(id=46, customer=customer, customer_id=1,
                cover_photo_path=str(photo), spread_photo_path=str(photo))
    menu.items = [MenuItem(id=1, menu_id=46, category=ItemCategory.MAIN, position=1,
                           title="Borscht", image_path=str(tmp_path / "missing.jpg"))]
    
    original_dpi = BookletRenderer.DPI
    BookletRenderer.DPI = 72
    try:
        with pytest.raises(ValueError, match="photograph missing"):
            BookletRenderer(tmp_path / "out").render(menu)
    finally:
        BookletRenderer.DPI = original_dpi


def test_dish_card_requests_photo_viewport_not_full_card(tmp_path, monkeypatch) -> None:
    """Regression: do not crop an image generated for the entire card."""
    from PIL import ImageDraw

    from app.render.booklet import A3BookletRenderer

    renderer = A3BookletRenderer(tmp_path)
    renderer.DPI = 72
    page = Image.new("RGB", (900, 900), "black")
    calls = []

    def fake_image(path, width, height):
        calls.append((width, height))
        return Image.new("RGB", (width, height), "red")

    monkeypatch.setattr(renderer, "_safe_item_image", fake_image)
    item = MenuItem(title="Кесадилья с сыром", image_path="placeholder.jpg")
    renderer._draw_item_card(page, (20, 20, 420, 320), item, None, compact=True)
    assert len(calls) == 1
    assert calls[0][0] == 400
    assert calls[0][1] < 300
    assert calls[0][1] > 0


def test_long_dish_title_is_not_shortened(tmp_path) -> None:
    from PIL import ImageDraw

    from app.render.booklet import A3BookletRenderer

    renderer = A3BookletRenderer(tmp_path)
    renderer.DPI = 72
    page = Image.new("RGB", (900, 400), "black")
    draw = ImageDraw.Draw(page)
    title = "Куриные фахитас с овощами и домашним соусом"
    renderer._fit_card_title(draw, title, (10, 10, 550, 150), compact=True)
    assert page.getbbox() is not None
