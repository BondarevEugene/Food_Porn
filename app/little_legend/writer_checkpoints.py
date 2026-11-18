"""Safe writer checkpoint application with monotonic revisions and job IDs."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.manuscript_repository import upsert_generated_chapter
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


class WriterCheckpoint(BaseModel):
    scene_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=8, max_length=120)
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=20000)


class CheckpointReceipt(BaseModel):
    applied: bool
    replayed: bool
    revision: int
    manuscript: StoryManuscript


def apply_writer_checkpoint(
    manuscript: StoryManuscript,
    checkpoint: WriterCheckpoint,
    *,
    scene_ids: set[str],
    recorded_jobs: dict[str, str],
) -> CheckpointReceipt:
    """Reject stale or duplicate work; never replace parent-approved chapters.

    recorded_jobs maps scene_id to the last committed job ID and is persisted
    by the caller in the same transaction as the manuscript.
    """
    if checkpoint.scene_id not in scene_ids:
        raise ValueError("Unknown story scene")
    current = next(
        (chapter for chapter in manuscript.chapters
         if chapter.scene_id == checkpoint.scene_id),
        None,
    )
    revision = current.revision if current else 0
    if recorded_jobs.get(checkpoint.scene_id) == checkpoint.job_id:
        if current is None:
            raise ValueError("Checkpoint receipt exists without a chapter")
        return CheckpointReceipt(
            applied=False, replayed=True, revision=revision,
            manuscript=manuscript.model_copy(deep=True),
        )
    if current is not None and current.approved:
        raise PermissionError("Approved chapter is immutable")
    if revision != checkpoint.expected_revision:
        raise ValueError("Stale writer checkpoint")
    updated = upsert_generated_chapter(
        manuscript,
        ChapterDraft(
            scene_id=checkpoint.scene_id,
            text=checkpoint.text,
            revision=revision + 1,
        ),
    )
    return CheckpointReceipt(
        applied=True, replayed=False, revision=revision + 1,
        manuscript=updated,
    )
