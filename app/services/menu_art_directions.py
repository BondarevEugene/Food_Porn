"""Deterministic creative direction catalog for restaurant menu artwork.

The design brief is for decorative imagery only. Customer portraits and menu
text must remain separately composed by the trusted Python renderer.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class MenuArtDirection:
    code: str
    theme: str
    title: str
    palette: str
    motif: str
    composition: str

    def prompt(self) -> str:
        return (
            f"Luxury restaurant editorial art direction: {self.title}. "
            f"Palette: {self.palette}. Decorative motifs: {self.motif}. "
            f"Composition: {self.composition}. "
            "Generate only background, borders and ornamental accents. "
            "No text, no letters, no logos, no people, no faces, no portraits, "
            "no plates obscuring reserved content areas. "
            "Leave generous clear zones for later typesetting and original customer photographs."
        )


_LIGHT = (
    "Ivory Champagne", "Parisian Patisserie", "Pearl Minimal", "Linen & Gold",
    "Provence Morning", "White Orchid", "Marble Atelier", "Silk Romance",
    "Classic Brasserie", "Alabaster", "Rosewater", "Swan Lake",
    "Champagne Garden", "French Riviera", "Cream Art Deco",
)
_DARK = (
    "Noir & Gold", "Midnight Velvet", "Obsidian", "Black Marble",
    "Royal Burgundy", "Candlelight", "Emerald Night", "Midnight Paris",
    "Copper Noir", "Dark Botanica", "Velvet Opera", "Graphite",
    "Celestial Dinner", "Sapphire Night", "Black Tie",
)
_COLOR = (
    "Mediterranean Citrus", "Botanical Love", "Tuscan Sunset",
    "Coral Riviera", "Terracotta", "Jade Garden", "Rose Garden",
    "Saffron", "Azure Coast", "Tropical Gourmet", "Peony Bloom",
    "Lavender Provence", "Ruby Celebration", "Amber Orchard",
    "Pistachio", "Ocean Pearl", "Pomegranate", "Golden Autumn",
    "Summer Berries", "Mosaic Atelier",
)
_MOTIFS = ("fine engraving", "soft floral silhouettes", "subtle foil ornament", "fine botanical linework", "minimal geometric filigree")
_LAYOUTS = ("asymmetric editorial margins", "restrained symmetrical framing", "airy modern columns", "art-deco corner detailing")


def all_directions() -> tuple[MenuArtDirection, ...]:
    result = []
    for theme, titles, palette in (
        ("light", _LIGHT, "ivory, champagne, pearl, warm white"),
        ("dark", _DARK, "deep charcoal, rich black, muted gold"),
        ("color", _COLOR, "rich harmonious seasonal colors"),
    ):
        for index, title in enumerate(titles):
            result.append(MenuArtDirection(
                code=f"{theme}-{index + 1:02d}",
                theme=theme,
                title=title,
                palette=palette,
                motif=_MOTIFS[index % len(_MOTIFS)],
                composition=_LAYOUTS[index % len(_LAYOUTS)],
            ))
    return tuple(result)


DIRECTIONS = all_directions()
BY_CODE = {direction.code: direction for direction in DIRECTIONS}


def choose_direction(theme: str, seed: str | int) -> MenuArtDirection:
    """Stable random selection; same theme and seed reproduce the same brief."""
    if theme not in ("light", "dark", "color"):
        raise ValueError(f"Unsupported restaurant theme: {theme}")
    candidates = [item for item in DIRECTIONS if item.theme == theme]
    digest = hashlib.sha256(f"{theme}:{seed}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).choice(candidates)
