"""Assemble a complete approved illustrated proof from private assets."""
from __future__ import annotations

from typing import Protocol

from app.little_legend.generated_art_store import illustration_key
from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


class ArtReader(Protocol):
    def get(self, *, key: str) -> bytes: ...


def assemble_private_book(
    *, title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
    owner_id: int, story_id: int, store: ArtReader,
) -> bytes:
    """Read approved generated assets only after all jobs have completed."""
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in manuscript.chapters
    ):
        raise PermissionError("Manuscript approval is required")
    expected = {node.id for node in graph.nodes}
    if not expected or {chapter.scene_id for chapter in manuscript.chapters} != expected:
        raise ValueError("Incomplete manuscript")
    if len(jobs) != len(expected) or {job.scene_id for job in jobs} != expected:
        raise PermissionError("All illustration jobs are required")
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if any(
        job.expected_revision != chapters[job.scene_id].revision
        or job.owner_id != owner_id or job.story_id != story_id
        or job.status != JobStatus.COMPLETED
        or job.provider_dispatched_at is None
        for job in jobs
    ):
        raise PermissionError("All illustrations must be completed and owned")
    images = {
        job.scene_id: store.get(key=illustration_key(
            owner_id=owner_id, story_id=story_id, job_id=job.job_id,
        ))
        for job in jobs
    }
    return render_illustrated_proof(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, illustrations=images,
        approved_scene_ids=expected,
    )
