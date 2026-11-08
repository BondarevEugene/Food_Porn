"""Fail closed when a purchased menu is missing real, distinct artwork."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from PIL import Image

from app.database.models import GenerationStatus, Menu



def validate_customer_photos(menu: Menu) -> None:
    """Reject missing or corrupt customer photos before paid AI generation."""
    for role, raw_path in (
        ("cover", menu.cover_photo_path),
        ("spread", menu.spread_photo_path),
    ):
        if not raw_path:
            raise ValueError(f"Customer {role} photo is required; upload it again")
        path = Path(raw_path)
        if not path.is_file():
            raise ValueError(f"Customer {role} photo is missing; upload it again")
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.width < 1 or image.height < 1:
                    raise ValueError("Empty image")
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"Customer {role} photo is unreadable; upload it again"
            ) from exc


def validate_menu_artwork(menu: Menu, placeholder: Path) -> None:
    selected = [item for item in menu.items if item.title != "—"]
    if not selected:
        raise ValueError("Menu contains no dishes")
    demo_hash = sha256(placeholder.read_bytes()).digest() if placeholder.is_file() else None
    seen: set[bytes] = set()
    for item in selected:
        if item.generation_status != GenerationStatus.DONE or not item.image_path:
            raise ValueError(f"Dish image unavailable: {item.title}")
        path = Path(item.image_path)
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.width < 512 or image.height < 512:
                raise ValueError(f"Dish image too small: {item.title}")
        digest = sha256(path.read_bytes()).digest()
        if digest == demo_hash or digest in seen:
            raise ValueError(f"Duplicate or demo photograph: {item.title}")
        seen.add(digest)


def validate_menu_files(menu: Menu, files: tuple[Path, ...], recipes: dict) -> None:
    names = {item.title for item in menu.items if item.title != "—"}
    if names - set(recipes):
        raise ValueError("Recipes do not cover all dishes")
    for path in files:
        if not path.is_file() or path.stat().st_size < 1024:
            raise ValueError(f"Incomplete output: {path.name}")
        if path.suffix == ".pdf" and not path.read_bytes()[:5] == b"%PDF-":
            raise ValueError(f"Invalid PDF: {path.name}")
