"""Pure manuscript edits preserve approval and revisions."""
import pytest

from app.little_legend.manuscript_repository import (
    ChapterEdit,
    approve_chapter,
    edit_chapter,
    upsert_generated_chapter,
)
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _manuscript():
    return StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="Первая версия")],
    )


def test_edit_increments_revision_without_mutating_original():
    original = _manuscript()
    changed = edit_chapter(
        original, "scene_1", ChapterEdit(text="Новая версия"),
    )
    assert original.chapters[0].text == "Первая версия"
    assert changed.chapters[0].revision == 2
    assert changed.chapters[0].text == "Новая версия"


def test_approved_chapter_is_locked():
    locked = approve_chapter(_manuscript(), "scene_1", True)
    with pytest.raises(PermissionError):
        edit_chapter(locked, "scene_1", ChapterEdit(text="Изменено"))
    with pytest.raises(PermissionError):
        upsert_generated_chapter(
            locked, ChapterDraft(scene_id="scene_1", text="AI", revision=2),
        )


def test_explicit_unlock_allows_edit():
    locked = approve_chapter(_manuscript(), "scene_1", True)
    unlocked = approve_chapter(locked, "scene_1", False)
    changed = edit_chapter(
        unlocked, "scene_1", ChapterEdit(text="Исправлено"),
    )
    assert changed.chapters[0].text == "Исправлено"
    assert not changed.chapters[0].approved


def test_stale_generated_revision_is_rejected():
    with pytest.raises(ValueError):
        upsert_generated_chapter(
            _manuscript(), ChapterDraft(
                scene_id="scene_1", text="Старая", revision=1,
            ),
        )
