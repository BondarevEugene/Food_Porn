"""Premium Little Legend digital book: palette and delivery contract."""
from io import BytesIO

import pytest
from PIL import Image as PILImage
from pypdf import PdfReader

from app.little_legend.digital_delivery_gate import validate_paid_digital_pdf
from app.little_legend.illustrated_pdf import (
    EDITION_PALETTES,
    PALETTE_GROUPS,
    render_illustrated_proof,
)
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


@pytest.mark.parametrize("palette", sorted(EDITION_PALETTES))
def test_premium_palette_preserves_delivery_contract(palette: str) -> None:
    graph = build_graph(["Звёздный сад"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Марта увидела звёздный сад.",
            approved=True,
        )],
    )
    image = BytesIO()
    PILImage.new("RGB", (700, 700), "white").save(image, format="PNG")
    pdf = render_illustrated_proof(
        title="Марта и сад", dedication="Для Марты",
        graph=graph, manuscript=manuscript,
        illustrations={"scene_1": image.getvalue()},
        approved_scene_ids={"scene_1"},
        edition="digital", palette=palette,
    )
    validate_paid_digital_pdf(pdf, expected_scenes=1)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "Звёздный сад" in text
    assert "Марта увидела звёздный сад." in text
    assert "EDITORIAL PROOF" not in text


def test_unknown_palette_is_rejected_before_rendering() -> None:
    with pytest.raises(ValueError, match="palette"):
        render_illustrated_proof(
            title="Test", dedication="", graph=build_graph(["Scene"]),
            manuscript=StoryManuscript(hero_name="Hero", chapters=[]),
            illustrations={}, approved_scene_ids=set(),
            edition="digital", palette="not-a-palette",
        )


def test_collection_has_fifteen_unique_accessible_color_sets() -> None:
    assert len(EDITION_PALETTES) == 15
    assert len(set(EDITION_PALETTES.values())) == 15
    for colors in EDITION_PALETTES.values():
        assert len(colors) == 5
        assert all(len(color) == 7 and color.startswith("#") for color in colors)


def test_palette_groups_are_exactly_five_each() -> None:
    assert set(PALETTE_GROUPS) == {"light", "vivid", "dark"}
    assert all(len(group) == 5 for group in PALETTE_GROUPS.values())
    assert {name for group in PALETTE_GROUPS.values() for name in group} == set(
        EDITION_PALETTES
    )
    for name in PALETTE_GROUPS["dark"]:
        background = EDITION_PALETTES[name][0]
        assert max(int(background[index:index + 2], 16) for index in (1, 3, 5)) < 90
