"""Writer contract: approvals, scene isolation and safe retries."""
import pytest

from app.little_legend.blueprint import quick_blueprint
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import (
    ChapterDraft,
    StoryManuscript,
    WritingPolicy,
    manuscript_review,
    write_manuscript,
)


class FakeWriter:
    def __init__(self):
        self.calls = []

    async def write_chapter(self, brief):
        self.calls.append(brief)
        return "Марта нашла волшебный ключ."


def setup():
    blueprint = quick_blueprint("Марта", age=7)
    blueprint.family_approved = True
    contract = contract_from_blueprint(blueprint, "Марта")
    return blueprint, contract, build_graph(["Начало", "Конец"])


@pytest.mark.asyncio
async def test_generates_chapters_with_same_hero_and_context():
    blueprint, contract, graph = setup()
    writer = FakeWriter()
    saved = []

    async def persist(chapter):
        saved.append(chapter.scene_id)

    result = await write_manuscript(
        writer, graph, contract, blueprint, StoryDesign(),
        policy=WritingPolicy(enabled=True), on_chapter=persist,
    )
    assert saved == ["scene_1", "scene_2"]
    assert len(result.chapters) == 2
    assert all(call["hero_brief"]["hero"]["hero_name"] == "Марта"
               for call in writer.calls)
    assert manuscript_review(result, graph)["ready_for_publication"] is False


@pytest.mark.asyncio
async def test_disabled_engine_never_calls_provider():
    blueprint, contract, graph = setup()
    writer = FakeWriter()
    with pytest.raises(PermissionError):
        await write_manuscript(
            writer, graph, contract, blueprint, StoryDesign(),
            policy=WritingPolicy(),
        )
    assert writer.calls == []


@pytest.mark.asyncio
async def test_approved_chapter_cannot_be_overwritten():
    blueprint, contract, graph = setup()
    existing = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="Утверждено", approved=True)],
    )
    writer = FakeWriter()
    with pytest.raises(PermissionError):
        await write_manuscript(
            writer, graph, contract, blueprint, StoryDesign(),
            policy=WritingPolicy(enabled=True), existing=existing,
            requested_scenes={"scene_1"},
        )
    assert not writer.calls


@pytest.mark.asyncio
async def test_regenerates_only_requested_unapproved_chapter():
    blueprint, contract, graph = setup()
    existing = StoryManuscript(
        hero_name="Марта",
        chapters=[
            ChapterDraft(scene_id="scene_1", text="Старый текст"),
            ChapterDraft(scene_id="scene_2", text="Утверждено", approved=True),
        ],
    )
    writer = FakeWriter()
    result = await write_manuscript(
        writer, graph, contract, blueprint, StoryDesign(),
        policy=WritingPolicy(enabled=True), existing=existing,
        requested_scenes={"scene_1"},
    )
    assert len(writer.calls) == 1
    assert result.chapters[0].revision == 2
    assert result.chapters[1].text == "Утверждено"


@pytest.mark.asyncio
async def test_unapproved_family_profile_blocks_generation():
    blueprint, contract, graph = setup()
    blueprint.family_approved = False
    writer = FakeWriter()
    with pytest.raises(PermissionError):
        await write_manuscript(
            writer, graph, contract, blueprint, StoryDesign(),
            policy=WritingPolicy(enabled=True),
        )
    assert writer.calls == []
