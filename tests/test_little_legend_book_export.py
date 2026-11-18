"""Regression tests for the authenticated illustrated book export contract."""
import base64
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.book_export import IllustratedBookRequest
from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _image() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (600, 600), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_book_export_decodes_explicitly_approved_images():
    raw = _image()
    payload = IllustratedBookRequest(
        illustrations={"scene_1": base64.b64encode(raw).decode("ascii")},
        approved_scene_ids={"scene_1"},
    )
    assert payload.decoded_images() == {"scene_1": raw}


def test_book_export_rejects_missing_approval():
    with pytest.raises(ValueError, match="approved"):
        IllustratedBookRequest(
            illustrations={"scene_1": base64.b64encode(_image()).decode("ascii")},
            approved_scene_ids={"scene_2"},
        )


def test_book_export_rejects_invalid_base64():
    payload = IllustratedBookRequest(
        illustrations={"scene_1": "not base64!"}, approved_scene_ids={"scene_1"},
    )
    with pytest.raises(ValueError, match="base64"):
        payload.decoded_images()


def test_book_export_builds_real_pdf():
    raw = _image()
    graph = build_graph(["A garden appears"])
    manuscript = StoryManuscript(
        hero_name="Marta",
        chapters=[ChapterDraft(scene_id="scene_1", text="Marta entered the garden.")],
    )
    payload = IllustratedBookRequest(
        illustrations={"scene_1": base64.b64encode(raw).decode("ascii")},
        approved_scene_ids={"scene_1"},
    )
    result = render_illustrated_proof(
        title="Marta's Garden",
        dedication="With love",
        graph=graph,
        manuscript=manuscript,
        illustrations=payload.decoded_images(),
        approved_scene_ids=payload.approved_scene_ids,
    )
    assert result.startswith(b"%PDF-")
    assert len(result) > 2000
