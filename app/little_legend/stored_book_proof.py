"""Assemble a proof from completed private illustrations, without paid calls."""
from __future__ import annotations

from app.little_legend.generated_art_store import (
    GeneratedArtStore,
    illustration_key,
    validate_generated_art,
)
from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


def assemble_stored_book_proof(
    *, store: GeneratedArtStore, owner_id: int, story_id: int,
    title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
) -> bytes:
    """Require a complete approved, revision-matched batch before storage reads."""
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Valid story ownership is required")
    nodes = graph.nodes
    expected = {node.id for node in nodes}
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if not expected or len(expected) != len(nodes):
        raise ValueError("Story scene IDs must be unique and nonempty")
    if (not manuscript.parent_approved or set(chapters) != expected
            or len(chapters) != len(manuscript.chapters)
            or any(not chapter.approved for chapter in chapters.values())):
        raise PermissionError("Complete approved manuscript required")
    if len(jobs) != len(expected) or {job.scene_id for job in jobs} != expected:
        raise PermissionError("Exactly one illustration job per scene is required")
    for job in jobs:
        if (job.owner_id != owner_id or job.story_id != story_id
                or job.status != JobStatus.COMPLETED
                or job.expected_revision != chapters[job.scene_id].revision):
            raise PermissionError("Illustration ownership, status or revision mismatch")
    images: dict[str, bytes] = {}
    for job in jobs:
        key = illustration_key(
            owner_id=owner_id, story_id=story_id, job_id=job.job_id,
        )
        image = store.get(key=key)
        validate_generated_art(image)
        images[job.scene_id] = image
    return render_illustrated_proof(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, illustrations=images,
        approved_scene_ids=expected,
    )
