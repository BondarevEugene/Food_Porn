"""A book release must match the PDF and recipient before delivery."""
from datetime import UTC, datetime

import pytest

from app.little_legend.book_delivery import BookDelivery, DeliveryStatus
from app.little_legend.book_release import seal_book_release
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.release_delivery import (
    complete_release_delivery,
    delivery_requires_reconciliation,
    flag_release_delivery_uncertain,
    prepare_release_delivery,
)
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


def _context():
    graph = build_graph(["The forest opens"])
    manuscript = StoryManuscript(
        hero_name="Marta", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="A gentle story.", approved=True,
        )],
    )
    jobs = [IllustrationJob(
        job_id="lli_delivery_1", owner_id=3, story_id=2,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
        provider_dispatched_at=datetime.now(UTC),
    )]
    pdf = b"%PDF-" + b"x" * 200
    release = seal_book_release(
        owner_id=3, story_id=2, graph=graph, manuscript=manuscript,
        jobs=jobs, pdf=pdf, editorial_approved=True,
    )
    delivery = BookDelivery(
        owner_id=3, story_id=2, pdf_sha256=release.pdf_sha256,
    )
    return graph, manuscript, jobs, pdf, release, delivery


def _prepare(graph, manuscript, jobs, pdf, release, delivery, **overrides):
    params = dict(
        release=release, delivery=delivery, owner_id=3, story_id=2,
        graph=graph, manuscript=manuscript, jobs=jobs,
        pdf=pdf, attempt_id="attempt-1",
    )
    params.update(overrides)
    return prepare_release_delivery(**params)


def test_verified_release_can_be_delivered_once():
    graph, manuscript, jobs, pdf, release, delivery = _context()
    sending = _prepare(graph, manuscript, jobs, pdf, release, delivery)
    assert sending.status == DeliveryStatus.SENDING
    assert delivery_requires_reconciliation(sending)
    sent = complete_release_delivery(
        release=release, delivery=sending,
        attempt_id="attempt-1", message_id=42,
    )
    assert sent.status == DeliveryStatus.SENT
    assert not delivery_requires_reconciliation(sent)
    with pytest.raises(PermissionError):
        _prepare(graph, manuscript, jobs, pdf, release, sent)


def test_modified_pdf_cannot_be_sent():
    graph, manuscript, jobs, pdf, release, delivery = _context()
    with pytest.raises(PermissionError, match="PDF changed"):
        _prepare(
            graph, manuscript, jobs, pdf[:-1] + b"y", release, delivery,
        )


def test_modified_manuscript_cannot_be_sent():
    graph, manuscript, jobs, pdf, release, delivery = _context()
    manuscript.chapters[0].text = "Edited after approval"
    with pytest.raises(PermissionError, match="content changed"):
        _prepare(graph, manuscript, jobs, pdf, release, delivery)


def test_foreign_owner_and_wrong_pdf_fingerprint_are_rejected():
    graph, manuscript, jobs, pdf, release, delivery = _context()
    with pytest.raises(PermissionError):
        _prepare(
            graph, manuscript, jobs, pdf, release, delivery, owner_id=4,
        )
    wrong_delivery = delivery.model_copy(update={"pdf_sha256": "f" * 64})
    with pytest.raises(PermissionError, match="does not match"):
        _prepare(graph, manuscript, jobs, pdf, release, wrong_delivery)


def test_uncertain_send_cannot_be_retried_automatically():
    graph, manuscript, jobs, pdf, release, delivery = _context()
    sending = _prepare(graph, manuscript, jobs, pdf, release, delivery)
    uncertain = flag_release_delivery_uncertain(
        release=release, delivery=sending, attempt_id="attempt-1",
    )
    assert delivery_requires_reconciliation(uncertain)
    with pytest.raises(PermissionError):
        _prepare(graph, manuscript, jobs, pdf, release, uncertain)
