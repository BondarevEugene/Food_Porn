"""Editorial PDF must reject incomplete or unapproved story content."""
from unittest.mock import Mock

import pytest

from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.story_graph import build_graph


def _render(graph=None, manuscript=None):
    return render_illustrated_proof(
        title="Forest", dedication="", graph=graph or build_graph(["Forest"]),
        manuscript=manuscript or Mock(
            hero_name="Marta", parent_approved=True,
            chapters=[Mock(scene_id="scene_1", approved=True, text="Hello")],
        ),
        illustrations={"scene_1": b"not-an-image"},
        approved_scene_ids={"scene_1"},
    )


def test_proof_rejects_unapproved_manuscript_before_image_decoding():
    manuscript = Mock(
        hero_name="Marta", parent_approved=False,
        chapters=[Mock(scene_id="scene_1", approved=True, text="Hello")],
    )
    with pytest.raises(PermissionError, match="Approved manuscript"):
        _render(manuscript=manuscript)


def test_proof_rejects_unapproved_chapter_before_image_decoding():
    manuscript = Mock(
        hero_name="Marta", parent_approved=True,
        chapters=[Mock(scene_id="scene_1", approved=False, text="Hello")],
    )
    with pytest.raises(PermissionError, match="Approved manuscript"):
        _render(manuscript=manuscript)


def test_proof_rejects_duplicate_chapters_before_image_decoding():
    chapter = Mock(scene_id="scene_1", approved=True, text="Hello")
    manuscript = Mock(
        hero_name="Marta", parent_approved=True,
        chapters=[chapter, chapter],
    )
    with pytest.raises(ValueError, match="unique scenes"):
        _render(manuscript=manuscript)
