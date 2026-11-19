"""Premium Little Legend digital book: palette and delivery contract."""
from io import BytesIO

import pytest
from PIL import Image as PILImage
from pypdf import PdfReader

from app.little_legend.digital_delivery_gate import validate_paid_digital_pdf
from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


@pytest.mark.parametrize("palette", ["lavender", "ocean", "sunrise"])
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
