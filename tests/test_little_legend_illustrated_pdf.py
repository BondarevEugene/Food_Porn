"""Illustrated proof uses in-memory approved assets and rejects unsafe inputs."""
from io import BytesIO

import pytest
from PIL import Image as PILImage

from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def sample():
    graph = build_graph(["Открытие сада"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Марта вошла в сад.", approved=True,
        )],
    )
    image = PILImage.new("RGB", (600, 600), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return graph, manuscript, output.getvalue()


def test_illustrated_pdf_contains_complete_story():
    graph, manuscript, image = sample()
    pdf = render_illustrated_proof(
        title="Сказка Марты", dedication="С любовью",
        graph=graph, manuscript=manuscript,
        illustrations={"scene_1": image}, approved_scene_ids={"scene_1"},
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


def test_unapproved_image_is_rejected():
    graph, manuscript, image = sample()
    with pytest.raises(PermissionError, match="approval"):
        render_illustrated_proof(
            title="Сказка", dedication="", graph=graph, manuscript=manuscript,
            illustrations={"scene_1": image}, approved_scene_ids=set(),
        )


def test_invalid_image_is_rejected():
    graph, manuscript, _ = sample()
    with pytest.raises(ValueError, match="image"):
        render_illustrated_proof(
            title="Сказка", dedication="", graph=graph, manuscript=manuscript,
            illustrations={"scene_1": b"not-an-image"},
            approved_scene_ids={"scene_1"},
        )
