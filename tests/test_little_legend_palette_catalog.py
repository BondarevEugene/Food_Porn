"""Palette selector API contract and renderer consistency."""
from app.little_legend.illustrated_pdf import EDITION_PALETTES, PALETTE_GROUPS
from app.little_legend.palette_catalog import book_palette_catalog
from app.little_legend.router import read_book_palettes


def test_palette_catalog_has_five_options_per_group() -> None:
    catalog = book_palette_catalog()
    assert catalog.default == "lavender"
    assert [group.id for group in catalog.groups] == ["light", "vivid", "dark"]
    assert [len(group.options) for group in catalog.groups] == [5, 5, 5]


def test_palette_catalog_matches_pdf_renderer_tokens() -> None:
    catalog = book_palette_catalog()
    seen = set()
    for group in catalog.groups:
        assert [item.id for item in group.options] == list(PALETTE_GROUPS[group.id])
        for item in group.options:
            assert item.id not in seen
            seen.add(item.id)
            assert item.title
            assert (
                item.background, item.accent, item.secondary,
                item.text, item.ornament,
            ) == EDITION_PALETTES[item.id]
    assert seen == set(EDITION_PALETTES)


async def test_public_palette_route_returns_catalog() -> None:
    catalog = await read_book_palettes()
    assert len(catalog.groups) == 3
    assert len(catalog.model_dump()["groups"][0]["options"]) == 5
