"""Book release fingerprints bind approved content, art jobs and PDF bytes."""
from datetime import UTC, datetime

import pytest

from app.little_legend.book_release import (
    seal_book_release,
    verify_book_release,
)
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


def _approved():
    graph = build_graph(["The forest opens"])
    manuscript = StoryManuscript(
        hero_name="Marta", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="A gentle story.", approved=True,
        )],
    )
    jobs = [IllustrationJob(
        job_id="lli_release_1", owner_id=3, story_id=2,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
        provider_dispatched_at=datetime.now(UTC),
    )]
    return graph, manuscript, jobs


def _seal(graph, manuscript, jobs):
    return seal_book_release(
        owner_id=3, story_id=2, graph=graph, manuscript=manuscript,
        jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
        editorial_approved=True,
    )


def test_approved_release_verifies_same_book():
    graph, manuscript, jobs = _approved()
    release = _seal(graph, manuscript, jobs)
    verify_book_release(
        release, owner_id=3, story_id=2, graph=graph,
        manuscript=manuscript, jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
    )


def test_manuscript_change_invalidates_release():
    graph, manuscript, jobs = _approved()
    release = _seal(graph, manuscript, jobs)
    manuscript.chapters[0].text = "A different story."
    with pytest.raises(PermissionError, match="content changed"):
        verify_book_release(
            release, owner_id=3, story_id=2, graph=graph,
            manuscript=manuscript, jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
        )


def test_art_job_change_invalidates_release():
    graph, manuscript, jobs = _approved()
    release = _seal(graph, manuscript, jobs)
    jobs[0].job_id = "lli_release_2"
    with pytest.raises(PermissionError, match="content changed"):
        verify_book_release(
            release, owner_id=3, story_id=2, graph=graph,
            manuscript=manuscript, jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
        )


def test_pdf_change_invalidates_release():
    graph, manuscript, jobs = _approved()
    release = _seal(graph, manuscript, jobs)
    with pytest.raises(PermissionError, match="PDF changed"):
        verify_book_release(
            release, owner_id=3, story_id=2, graph=graph,
            manuscript=manuscript, jobs=jobs, pdf=b"%PDF-" + b"y" * 200,
        )


def test_unapproved_editorial_cannot_seal_release():
    graph, manuscript, jobs = _approved()
    with pytest.raises(PermissionError, match="not approved"):
        seal_book_release(
            owner_id=3, story_id=2, graph=graph, manuscript=manuscript,
            jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
            editorial_approved=False,
        )


def test_foreign_owner_cannot_verify_release():
    graph, manuscript, jobs = _approved()
    release = _seal(graph, manuscript, jobs)
    with pytest.raises(PermissionError, match="not found"):
        verify_book_release(
            release, owner_id=4, story_id=2, graph=graph,
            manuscript=manuscript, jobs=jobs, pdf=b"%PDF-" + b"x" * 200,
        )
