"""Production orchestration: approvals before provider calls and real PDF output."""
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.book_production import produce_illustrated_book
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


class Illustrator:
    def __init__(self):
        self.calls = []

    async def generate_scene(self, *, scene, hero, style, continuity=""):
        self.calls.append(scene.id)
        output = BytesIO()
        Image.new("RGB", (600, 600), "white").save(output, "PNG")
        return output.getvalue()


def _approved():
    graph = build_graph(["A garden opens"])
    manuscript = StoryManuscript(
        hero_name="Marta",
        parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Marta discovered a garden.",
            approved=True,
        )],
    )
    return graph, manuscript


@pytest.mark.asyncio
async def test_approved_book_generates_real_pdf():
    graph, manuscript = _approved()
    provider = Illustrator()
    pdf = await produce_illustrated_book(
        illustrator=provider, title="Marta's Garden", dedication="For Marta",
        graph=graph, manuscript=manuscript, style="watercolor",
        approved_scene_ids={"scene_1"},
    )
    assert pdf.startswith(b"%PDF-")
    assert provider.calls == ["scene_1"]


@pytest.mark.asyncio
async def test_unapproved_manuscript_does_not_call_provider():
    graph, manuscript = _approved()
    manuscript.parent_approved = False
    provider = Illustrator()
    with pytest.raises(PermissionError, match="manuscript"):
        await produce_illustrated_book(
            illustrator=provider, title="Marta", dedication="",
            graph=graph, manuscript=manuscript, style="storybook",
            approved_scene_ids={"scene_1"},
        )
    assert provider.calls == []


@pytest.mark.asyncio
async def test_missing_scene_approval_does_not_call_provider():
    graph, manuscript = _approved()
    provider = Illustrator()
    with pytest.raises(PermissionError, match="scene"):
        await produce_illustrated_book(
            illustrator=provider, title="Marta", dedication="",
            graph=graph, manuscript=manuscript, style="storybook",
            approved_scene_ids=set(),
        )
    assert provider.calls == []
