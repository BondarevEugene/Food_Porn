"""Assemble a complete approved illustrated proof from private assets."""
from __future__ import annotations

from typing import Protocol

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.stored_book_proof import assemble_stored_book_proof
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


class ArtReader(Protocol):
    def get(self, *, key: str) -> bytes: ...


def assemble_private_book(
    *, title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
    owner_id: int, story_id: int, store: ArtReader,
) -> bytes:
    """Use the single fail-closed assembly path for private PDF delivery."""
    if any(job.provider_dispatched_at is None for job in jobs):
        raise PermissionError("All illustrations must have been dispatched")
    return assemble_stored_book_proof(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, jobs=jobs, owner_id=owner_id,
        story_id=story_id, store=store,
    )
