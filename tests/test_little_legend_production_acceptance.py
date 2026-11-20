"""Cross-module production acceptance without paid provider calls or live secrets.

These tests drive one coherent book through conductor, customer journey,
release preflight and PDF-worker orchestration; external effects are mocked.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.little_legend import paid_book_worker as pdf_worker
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.production_conductor import Stage, classify
from app.little_legend.production_journey import JourneyStage, stage_for
from app.little_legend.release_readiness import assess_paid_release
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def complete_book():
    draft = StoryDraft(outline_approved=True)
    graph = build_graph(["The journey begins", "A safe return"])
    draft = draft.model_copy(update={"graph": graph, "parent_sketch": object()})
    draft.manuscript = StoryManuscript(
        hero_name=draft.hero, parent_approved=True,
        chapters=[
            ChapterDraft(scene_id=node.id, text="A reviewed chapter.",
                         approved=True, revision=2)
            for node in graph.nodes
        ],
    )
    draft.image_ai_consent.active = True
    decision = draft.editorial_decision
    decision.hero_fidelity_reviewed = True
    decision.age_appropriateness_reviewed = True
    decision.narrative_continuity_reviewed = True
    decision.parent_final_approval = True
    jobs = [
        IllustrationJob(
            job_id=f"illustration-{index:04d}", story_id=42, owner_id=77,
            scene_id=node.id, expected_revision=2,
            estimated_cost_usd=0.05, status="completed",
            provider_dispatched_at=datetime.now(UTC),
        )
        for index, node in enumerate(graph.nodes)
    ]
    return draft, jobs


def test_approved_paid_book_advances_through_all_release_views():
    draft, jobs = complete_book()
    statuses = [job.status.value for job in jobs]
    assert classify(
        draft, writer_count=0, art_count=len(jobs), art_statuses=statuses,
    ) == Stage.WAITING_EDITORIAL
    assert stage_for(
        draft=draft, payment_verified=True, fulfillment_status="pending",
        delivery_started=False, delivered=False, writers=["completed"],
        illustrations=statuses,
    ) == (JourneyStage.PRODUCING_PDF, "wait")
    result = assess_paid_release(
        quote_id=9, draft=draft, payment_verified=True,
        fulfillment_status="pending", art_jobs=jobs,
    )
    assert result.release_ready
    assert result.completed_scenes == result.total_scenes == 2
    assert not result.blockers


def test_stale_illustration_is_never_exported_even_when_status_completed():
    draft, jobs = complete_book()
    jobs[0].expected_revision = 1
    result = assess_paid_release(
        quote_id=9, draft=draft, payment_verified=True,
        fulfillment_status="pending", art_jobs=jobs,
    )
    assert not result.release_ready
    assert "illustration_revision_stale" in result.blockers


def test_missing_payment_blocks_fully_approved_book():
    draft, jobs = complete_book()
    result = assess_paid_release(
        quote_id=9, draft=draft, payment_verified=False,
        fulfillment_status="pending", art_jobs=jobs,
    )
    assert not result.release_ready
    assert "payment_not_verified" in result.blockers


def test_revoked_final_approval_blocks_pdf_even_with_all_art():
    draft, jobs = complete_book()
    draft.editorial_decision.parent_final_approval = False
    result = assess_paid_release(
        quote_id=9, draft=draft, payment_verified=True,
        fulfillment_status="pending", art_jobs=jobs,
    )
    assert not result.release_ready
    assert "final_parent_editorial_approval_missing" in result.blockers


@pytest.mark.asyncio
async def test_pdf_worker_idle_does_not_dispatch_external_effects(monkeypatch):
    resume = AsyncMock(return_value=False)
    claim = AsyncMock(return_value=None)
    render = AsyncMock()
    deliver = AsyncMock()
    monkeypatch.setattr(pdf_worker, "_resume_ready_delivery", resume)
    monkeypatch.setattr(pdf_worker, "_claim_one", claim)
    monkeypatch.setattr(pdf_worker, "_render", render)
    monkeypatch.setattr(pdf_worker, "_deliver", deliver)
    assert await pdf_worker.process_one() is False
    resume.assert_awaited_once()
    claim.assert_awaited_once()
    render.assert_not_awaited()
    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_pdf_worker_resumes_ready_delivery_without_new_pdf(monkeypatch):
    resume = AsyncMock(return_value=True)
    claim = AsyncMock()
    render = AsyncMock()
    monkeypatch.setattr(pdf_worker, "_resume_ready_delivery", resume)
    monkeypatch.setattr(pdf_worker, "_claim_one", claim)
    monkeypatch.setattr(pdf_worker, "_render", render)
    assert await pdf_worker.process_one() is True
    claim.assert_not_awaited()
    render.assert_not_awaited()
