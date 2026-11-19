"""Stable, public design-token catalog for Little Legend palette selectors.

The palette catalog contains no user, order, photograph or payment data.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.little_legend.illustrated_pdf import EDITION_PALETTES, PALETTE_GROUPS

GROUP_TITLES = {
    "light": "Нежные",
    "vivid": "Яркие",
    "dark": "Тёмные",
}
PALETTE_TITLES = {
    "lavender": "Лаванда",
    "blush": "Розовый",
    "sage": "Шалфей",
    "champagne": "Шампань",
    "sky": "Небо",
    "sunrise": "Рассвет",
    "ocean": "Океан",
    "coral": "Коралл",
    "sunflower": "Подсолнух",
    "emerald": "Изумруд",
    "midnight": "Полночь",
    "royal": "Пурпур",
    "forest": "Тёмный лес",
    "burgundy": "Бордо",
    "obsidian": "Обсидиан",
}


class PaletteOption(BaseModel):
    id: str
    title: str
    background: str
    accent: str
    secondary: str
    text: str
    ornament: str


class PaletteGroup(BaseModel):
    id: str
    title: str
    options: list[PaletteOption]


class PaletteCatalog(BaseModel):
    default: str
    groups: list[PaletteGroup]


def book_palette_catalog() -> PaletteCatalog:
    """Return the exact renderer-supported options in deterministic order."""
    if set(PALETTE_TITLES) != set(EDITION_PALETTES):
        raise ValueError("Palette labels are out of sync with renderer")
    groups = []
    for group_id, names in PALETTE_GROUPS.items():
        options = []
        for name in names:
            background, accent, secondary, ink, ornament = EDITION_PALETTES[name]
            options.append(PaletteOption(
                id=name, title=PALETTE_TITLES[name],
                background=background, accent=accent,
                secondary=secondary, text=ink, ornament=ornament,
            ))
        groups.append(PaletteGroup(
            id=group_id, title=GROUP_TITLES[group_id], options=options,
        ))
    return PaletteCatalog(default="lavender", groups=groups)
