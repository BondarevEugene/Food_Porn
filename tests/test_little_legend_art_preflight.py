"""Book-wide art preflight catches blockers before a paid provider request."""
import pytest

from app.little_legend.art_preflight import inspect_book_art, require_book_art_ready
from app.little_legend.blueprint import BookBlueprint, CharacterProfile
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def approved_book():
    graph = build_graph(["Марта входит в сад", "Марта находит звезду"])
    graph.nodes[0].illustration_prompt = "Марта открывает ворота"
    graph.nodes[1].illustration_prompt = "Марта берёт звезду"
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[
            ChapterDraft(scene_id=node.id, text="Глава", approved=True)
            for node in graph.nodes
        ],
    )
    return StoryDraft(
        hero="Марта", graph=graph, manuscript=manuscript,
        blueprint=BookBlueprint(characters=[
            CharacterProfile(name="Марта", appearance="Рыжие волосы"),
        ]),
    )


def test_approved_book_has_scene_by_scene_readiness():
    report = inspect_book_art(approved_book())
    assert report.ready
    assert report.scenes_total == 2
    assert report.scenes_ready == 2
    assert all(scene.prompt_chars > 0 for scene in report.scenes)
    assert report.photo_likeness_supported is False


def test_preflight_catches_oversized_late_scene_before_queue():
    draft = approved_book()
    draft.graph.nodes[1].summary = "С" * 1980
    report = inspect_book_art(draft)
    assert not report.ready
    assert report.scenes_ready == 1
    assert report.scenes[1].scene_id == "scene_2"
    assert "oversized" in report.scenes[1].blockers[0]
    with pytest.raises(PermissionError, match="scene_2"):
        require_book_art_ready(draft)


def test_preflight_requires_approval_for_every_chapter():
    draft = approved_book()
    draft.manuscript.chapters[1].approved = False
    report = inspect_book_art(draft)
    assert not report.ready
    assert "not approved" in report.scenes[1].blockers[0]


def test_preflight_rejects_missing_chapters_and_parent_approval():
    draft = approved_book()
    draft.manuscript.parent_approved = False
    draft.manuscript.chapters.pop()
    report = inspect_book_art(draft)
    assert not report.ready
    assert "Parent has not approved the manuscript" in report.blockers
    assert "Manuscript chapters do not match the story graph" in report.blockers


def test_preflight_rejects_oversized_hero_identity():
    draft = approved_book()
    draft.blueprint.characters[0].appearance = "А" * 1200
    draft.blueprint.characters[0].visual_identity_notes = "Б" * 1200
    report = inspect_book_art(draft)
    assert not report.ready
    assert any("continuity exceeds" in item for item in report.blockers)


def test_preflight_rejects_missing_story_graph():
    draft = StoryDraft(hero="Марта")
    report = inspect_book_art(draft)
    assert not report.ready
    assert report.scenes_total == 0
    assert "Story graph is missing" in report.blockers


def test_parent_identity_edit_invalidates_previously_ready_book():
    from app.little_legend.character_identity import IdentityBible, VisualIdentity

    draft = approved_book()
    assert inspect_book_art(draft).ready
    draft.identity_bible = IdentityBible(
        hero_name="Марта",
        identity=VisualIdentity(
            parent_reviewed_description=True, hair="А" * 200,
            eyes="Б" * 200, face="В" * 300,
            proportions="Г" * 300, clothing_signature="Д" * 300,
        ),
    )
    report = inspect_book_art(draft)
    assert not report.ready
    assert any("continuity limit" in blocker for blocker in report.blockers)


def test_parent_changes_other_chapter_after_book_was_ready():
    draft = approved_book()
    assert inspect_book_art(draft).ready
    draft.manuscript.chapters[0].approved = False
    report = inspect_book_art(draft)
    assert not report.ready
    assert report.scenes_ready == 1
    with pytest.raises(PermissionError, match="Chapter is not approved"):
        require_book_art_ready(draft)
