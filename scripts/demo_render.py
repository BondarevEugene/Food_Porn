"""
==========================================================
FOOD_PORN

Module: Offline Demo Renderer
Layer: Script

Responsibilities:
    - Build deterministic sample menu data
    - Render A3 previews without Telegram, Neon, or OpenAI
    - Support local visual verification of booklet changes
==========================================================
"""

from pathlib import Path

from PIL import Image, ImageDraw

from app.database.models import Customer, GenerationStatus, ItemCategory, Language, Menu, MenuItem
from app.render.booklet import BookletRenderer

ROOT = Path("storage/demo")
ROOT.mkdir(parents=True, exist_ok=True)


def picture(path: Path, color: tuple[int, int, int], label: str, size=(900, 900)) -> Path:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.text((40, 40), label, fill=(245, 225, 190))
    image.save(path, "JPEG", quality=92)
    return path


cover = picture(ROOT / "cover.jpg", (65, 25, 20), "COVER PHOTO", (1000, 1500))
spread = picture(ROOT / "spread.jpg", (45, 30, 35), "SPREAD PHOTO", (1000, 1500))

customer = Customer(
    telegram_user_id=1,
    phone="+380000000000",
    name="Анна",
    language=Language.RU,
    country="Украина",
    city="Киев",
)
menu = Menu(
    id=999,
    customer=customer,
    customer_id=1,
    language=Language.RU,
    cover_photo_path=str(cover),
    spread_photo_path=str(spread),
)
names = {
    ItemCategory.MAIN: ["Паста Карбонара", "Стейк с овощами", "Ризотто"],
    ItemCategory.APPETIZER: ["Брускетта", "Сырная тарелка", "Креветки"],
    ItemCategory.DESSERT: ["Тирамису", "Шоколадный фондан", "Чизкейк"],
    ItemCategory.DRINK: ["Вода с лимоном", "Белое вино", "Красное вино"],
}
items = []
item_id = 0
for category, titles in names.items():
    for index, title in enumerate(titles, 1):
        item_id += 1
        image_path = picture(ROOT / f"item_{item_id}.jpg", (70 + item_id * 5, 45, 24), title)
        items.append(
            MenuItem(
                id=item_id,
                menu_id=menu.id,
                category=category,
                position=index,
                title=title,
                image_path=str(image_path),
                generation_status=GenerationStatus.DONE,
            )
        )
menu.items = items

result = BookletRenderer(Path("storage/generated")).render(menu)
print(result.outside_preview)
print(result.inside_preview)
print(result.print_pdf)
