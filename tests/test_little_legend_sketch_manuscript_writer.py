"""Tests for parent-sourced, consent-gated sequential literary writing."""
import pytest

from app.little_legend.blueprint import quick_blueprint
from app.little_legend.client_sketch import ParentSketch, outline_from_sketch
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.sketch_manuscript_writer import write_sketch_manuscript
from app.little_legend.sketch_writer_briefs import SketchWritingSettings
from app.little_legend.story_writer import WritingPolicy


class FakeWriter:
    def __init__(self):
        self.briefs = []

    async def write_chapter(self, brief):
        self.briefs.append(brief)
        return f"Глава {brief['chapter']}: Марта выбирает путь."


def args():
    sketch = ParentSketch(
        premise="Марта находит карту забытого волшебного острова.",
        moments=["Она встречает сову.", "Они находят маяк."],
        avoid=["жестокость"],
    )
    outline = outline_from_sketch(sketch, chapter_count=3)
    blueprint = quick_blueprint("Марта")
    blueprint.family_approved = True
    return dict(
        sketch=sketch, graph=outline.graph,
        contract=contract_from_blueprint(blueprint, "Марта"),
        blueprint=blueprint, design=outline.design,
        settings=SketchWritingSettings(), policy=WritingPolicy(enabled=True),
        outline_approved=True, external_processing_authorized=True,
    )


@pytest.mark.asyncio
async def test_writer_uses_original_source_and_prior_chapter():
    provider = FakeWriter()
    checkpoints = []

    async def persist(chapter):
        checkpoints.append(chapter.scene_id)

    manuscript = await write_sketch_manuscript(
        provider=provider, on_chapter=persist, **args(),
    )
    assert len(manuscript.chapters) == 3
    assert checkpoints == ["scene_1", "scene_2", "scene_3"]
    assert provider.briefs[1]["continuity"]["previous_chapters"][0]["written_text"]
    assert all("жестокость" in b["parent_original"]["excluded_topics"]
               for b in provider.briefs)


@pytest.mark.asyncio
async def test_no_external_calls_without_authorization():
    provider = FakeWriter()
    options = args()
    options["external_processing_authorized"] = False
    with pytest.raises(PermissionError, match="authorization"):
        await write_sketch_manuscript(provider=provider, **options)
    assert provider.briefs == []


@pytest.mark.asyncio
async def test_no_external_calls_without_outline_approval():
    provider = FakeWriter()
    options = args()
    options["outline_approved"] = False
    with pytest.raises(PermissionError, match="outline"):
        await write_sketch_manuscript(provider=provider, **options)
    assert provider.briefs == []
