"""Checkpoint idempotency, stale writes and parental approval protection."""
import pytest

from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_checkpoints import (
    WriterCheckpoint,
    apply_writer_checkpoint,
)


def checkpoint(job="writer-job-123", expected=0, text="Марта нашла ключ."):
    return WriterCheckpoint(
        scene_id="scene_1", job_id=job,
        expected_revision=expected, text=text,
    )


def empty():
    return StoryManuscript(hero_name="Марта")


def test_first_checkpoint_and_replay_are_idempotent():
    first = apply_writer_checkpoint(
        empty(), checkpoint(), scene_ids={"scene_1"}, recorded_jobs={},
    )
    assert first.applied
    assert first.revision == 1
    replay = apply_writer_checkpoint(
        first.manuscript, checkpoint(),
        scene_ids={"scene_1"}, recorded_jobs={"scene_1": "writer-job-123"},
    )
    assert replay.replayed
    assert not replay.applied
    assert replay.manuscript.chapters[0].text == "Марта нашла ключ."


def test_stale_job_cannot_overwrite_newer_chapter():
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="Новый текст", revision=2)],
    )
    with pytest.raises(ValueError, match="Stale"):
        apply_writer_checkpoint(
            manuscript, checkpoint(job="writer-job-456", expected=1),
            scene_ids={"scene_1"}, recorded_jobs={},
        )


def test_approved_chapter_cannot_be_overwritten():
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Одобрено", approved=True,
        )],
    )
    with pytest.raises(PermissionError):
        apply_writer_checkpoint(
            manuscript, checkpoint(job="writer-job-456", expected=1),
            scene_ids={"scene_1"}, recorded_jobs={},
        )


def test_unknown_scene_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        apply_writer_checkpoint(
            empty(), checkpoint(), scene_ids={"scene_2"}, recorded_jobs={},
        )
