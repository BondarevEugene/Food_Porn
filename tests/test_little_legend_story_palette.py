"""Palette selection is durable and validated at the story boundary."""
import pytest
from pydantic import ValidationError

from app.little_legend.illustrated_pdf import EDITION_PALETTES, PALETTE_GROUPS
from app.little_legend.router import StoryDraft


@pytest.mark.parametrize("palette", sorted(EDITION_PALETTES))
def test_all_book_palettes_round_trip_in_story_draft(palette: str) -> None:
    draft = StoryDraft(palette=palette)
    restored = StoryDraft.model_validate_json(draft.model_dump_json())
    assert restored.palette == palette


def test_legacy_draft_uses_lavender_without_requiring_migration() -> None:
    assert StoryDraft.model_validate({}).palette == "lavender"


@pytest.mark.parametrize("palette", ["unknown", "", "DARK", "#000000"])
def test_untrusted_palette_is_rejected(palette: str) -> None:
    with pytest.raises(ValidationError):
        StoryDraft(palette=palette)


def test_palette_groups_cover_every_supported_choice() -> None:
    assert len(EDITION_PALETTES) == 15
    assert all(len(names) == 5 for names in PALETTE_GROUPS.values())
    assert {name for names in PALETTE_GROUPS.values() for name in names} == set(
        EDITION_PALETTES
    )
