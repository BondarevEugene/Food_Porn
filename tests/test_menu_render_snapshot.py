"""The CPU-bound PDF renderer must not read live SQLAlchemy ORM objects."""
from types import SimpleNamespace

from app.render.booklet import menu_render_snapshot


def test_snapshot_is_detached_plain_python_values():
    customer = SimpleNamespace(name="Recipient", language="ru")
    item = SimpleNamespace(
        id=11, title="Soup", category="soup", position=1,
        image_path="/generated/soup.png", meal_slot="lunch",
    )
    menu = SimpleNamespace(
        id=73, customer=customer, items=[item],
        cover_photo_path="/photos/cover.jpg",
        spread_photo_path="/photos/spread.jpg",
        meal_period="full_day",
    )
    frozen = menu_render_snapshot(menu)
    item.title = "Changed after snapshot"
    customer.name = "Changed after snapshot"
    menu.items.append(item)
    assert frozen.id == 73
    assert frozen.customer.name == "Recipient"
    assert frozen.items[0].title == "Soup"
    assert len(frozen.items) == 1
    assert frozen.items[0] is not item
    assert frozen.customer is not customer
    assert frozen.cover_photo_path == "/photos/cover.jpg"
