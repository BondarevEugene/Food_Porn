"""Bind a verified book release to a single safe delivery attempt.

Pure domain orchestration: callers must persist the new delivery state before
sending the PDF and reconcile ambiguous Telegram responses externally.
"""
from __future__ import annotations

from app.little_legend.book_delivery import (
    BookDelivery,
    DeliveryStatus,
    begin_delivery,
    confirm_delivery,
    mark_uncertain,
)
from app.little_legend.book_release import BookRelease, verify_book_release
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


def prepare_release_delivery(
    *, release: BookRelease, delivery: BookDelivery,
    owner_id: int, story_id: int, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
    pdf: bytes, attempt_id: str,
) -> BookDelivery:
    """Reject a stale release or wrong recipient before reserving a send."""
    verify_book_release(
        release, owner_id=owner_id, story_id=story_id,
        graph=graph, manuscript=manuscript, jobs=jobs, pdf=pdf,
    )
    if (delivery.owner_id != owner_id or delivery.story_id != story_id
            or delivery.pdf_sha256 != release.pdf_sha256):
        raise PermissionError("Delivery does not match the approved book release")
    return begin_delivery(delivery, attempt_id=attempt_id)


def complete_release_delivery(
    *, release: BookRelease, delivery: BookDelivery,
    attempt_id: str, message_id: int,
) -> BookDelivery:
    """Only acknowledge the same book and active dispatch attempt."""
    if (delivery.owner_id != release.owner_id
            or delivery.story_id != release.story_id
            or delivery.pdf_sha256 != release.pdf_sha256):
        raise PermissionError("Delivery does not match the approved book release")
    return confirm_delivery(
        delivery, attempt_id=attempt_id, message_id=message_id,
    )


def flag_release_delivery_uncertain(
    *, release: BookRelease, delivery: BookDelivery, attempt_id: str,
) -> BookDelivery:
    """Prevent automatic re-sends after ambiguous provider failures."""
    if (delivery.owner_id != release.owner_id
            or delivery.story_id != release.story_id
            or delivery.pdf_sha256 != release.pdf_sha256):
        raise PermissionError("Delivery does not match the approved book release")
    return mark_uncertain(delivery, attempt_id=attempt_id)


def delivery_requires_reconciliation(delivery: BookDelivery) -> bool:
    return delivery.status in {DeliveryStatus.SENDING, DeliveryStatus.UNCERTAIN}
