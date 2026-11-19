"""Fail-closed assembly and immutable release package for an approved book.

This layer performs no paid calls or Telegram sends. The caller must load
owner-scoped records, persist release/delivery state and dispatch separately.
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from app.little_legend.book_delivery import BookDelivery
from app.little_legend.book_release import BookRelease, seal_book_release, verify_book_release
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.private_book_assembly import ArtReader, assemble_private_book
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


class ReleasePackage(BaseModel):
    release: BookRelease
    delivery: BookDelivery
    pdf: bytes = Field(min_length=100)

    def verified_pdf(self, *, owner_id: int, story_id: int) -> bytes:
        """Verify immutable bytes and recipient even when package is deserialized."""
        if self.release.owner_id != owner_id or self.release.story_id != story_id:
            raise PermissionError("Book release belongs to another owner or story")
        if (
            self.delivery.owner_id != owner_id
            or self.delivery.story_id != story_id
            or self.delivery.pdf_sha256 != self.release.pdf_sha256
        ):
            raise PermissionError("Book delivery does not match the release")
        if not self.pdf.startswith(b"%PDF-"):
            raise ValueError("Release package does not contain a PDF")
        if hashlib.sha256(self.pdf).hexdigest() != self.release.pdf_sha256:
            raise PermissionError("Book PDF differs from sealed release")
        return self.pdf


def build_release_package(
    *, owner_id: int, story_id: int, title: str, dedication: str,
    graph: StoryGraph, manuscript: StoryManuscript,
    jobs: list[IllustrationJob], store: ArtReader,
    editorial_approved: bool,
) -> ReleasePackage:
    """Read all private illustrations and seal one consistent book snapshot."""
    if not editorial_approved:
        raise PermissionError("Editorial approval is required before book assembly")
    if any(job.owner_id != owner_id or job.story_id != story_id for job in jobs):
        raise PermissionError("Illustration batch belongs to another owner or story")
    pdf = assemble_private_book(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, jobs=jobs, owner_id=owner_id,
        story_id=story_id, store=store,
    )
    release = seal_book_release(
        owner_id=owner_id, story_id=story_id, graph=graph,
        manuscript=manuscript, jobs=jobs, pdf=pdf,
        editorial_approved=editorial_approved,
    )
    verify_book_release(
        release, owner_id=owner_id, story_id=story_id,
        graph=graph, manuscript=manuscript, jobs=jobs, pdf=pdf,
    )
    delivery = BookDelivery(
        owner_id=owner_id, story_id=story_id, pdf_sha256=release.pdf_sha256,
    )
    package = ReleasePackage(release=release, delivery=delivery, pdf=pdf)
    package.verified_pdf(owner_id=owner_id, story_id=story_id)
    return package
