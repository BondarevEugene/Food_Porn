"""Immutable publication fingerprint for an approved Little Legend book.

A release snapshot binds scene order, approved manuscript revisions, art job
identifiers and verified PDF bytes. It contains no child text or image data.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.production_readiness import assess_production
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


class BookRelease(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    revision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scene_count: int = Field(ge=1, le=40)


def manuscript_fingerprint(
    *, graph: StoryGraph, manuscript: StoryManuscript,
    jobs: list[IllustrationJob],
) -> str:
    """Hash the approved content and art references, never expose the payload."""
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    by_scene = {job.scene_id: job for job in jobs}
    payload = {
        "hero": manuscript.hero_name,
        "parent_approved": manuscript.parent_approved,
        "scenes": [
            {
                "id": node.id, "order": node.order,
                "node": node.model_dump(mode="json"),
                "chapter": chapters[node.id].model_dump(mode="json"),
                "art_job_id": by_scene[node.id].job_id,
                "art_revision": by_scene[node.id].expected_revision,
            }
            for node in sorted(graph.nodes, key=lambda item: item.order)
        ],
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def seal_book_release(
    *, owner_id: int, story_id: int, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
    pdf: bytes, editorial_approved: bool,
) -> BookRelease:
    """Seal only complete approved production with a nonempty PDF."""
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=editorial_approved, pdf_verified=True,
    )
    if not report.ready_for_delivery:
        raise PermissionError("Book production is not approved for release")
    if not pdf.startswith(b"%PDF-") or len(pdf) < 100:
        raise ValueError("Verified PDF bytes are required")
    return BookRelease(
        owner_id=owner_id, story_id=story_id,
        revision_fingerprint=manuscript_fingerprint(
            graph=graph, manuscript=manuscript, jobs=jobs,
        ),
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        scene_count=len(graph.nodes),
    )


def verify_book_release(
    release: BookRelease, *, owner_id: int, story_id: int,
    graph: StoryGraph, manuscript: StoryManuscript,
    jobs: list[IllustrationJob], pdf: bytes,
) -> None:
    """Reject stale manuscripts, changed artwork references or PDF bytes."""
    if release.owner_id != owner_id or release.story_id != story_id:
        raise PermissionError("Book release not found")
    if len(graph.nodes) != release.scene_count:
        raise PermissionError("Book scene count changed")
    if hashlib.sha256(pdf).hexdigest() != release.pdf_sha256:
        raise PermissionError("Book PDF changed since approval")
    if manuscript_fingerprint(
        graph=graph, manuscript=manuscript, jobs=jobs,
    ) != release.revision_fingerprint:
        raise PermissionError("Book content changed since approval")
