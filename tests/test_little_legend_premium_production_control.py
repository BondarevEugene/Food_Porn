"""Batch-level premium production audit and explicit editorial release gates."""
from datetime import UTC, datetime

import pytest

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_production_control import audit_premium_batch
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.writer_queue import JobStatus


def _batch():
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE, reference_ids=["photo1", "photo2", "photo3"],
        chapter_moments=[("At the river", "Inside the tower")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=11, story_id=22, plan=plan, chapter_revisions=[2],
    )
    jobs = [
        IllustrationJob(
            job_id=f"lli_batch_{index:04d}_abcdef", owner_id=11, story_id=22,
            scene_id=request.moment_id,
            expected_revision=request.expected_revision,
            estimated_cost_usd=request.estimated_micro_usd / 1_000_000,
            status=JobStatus.COMPLETED,
            premium_manifest_fingerprint=manifest.fingerprint,
            premium_story_fingerprint="a" * 64,
            premium_manifest_snapshot=manifest.model_dump(mode="json"),
            premium_plan_snapshot=plan.model_dump(mode="json"),
        )
        for index, request in enumerate(manifest.requests)
    ]
    return jobs


def test_complete_batch_requires_explicit_cover_and_scene_approvals():
    jobs = _batch()
    report = audit_premium_batch(jobs=jobs)
    assert report.expected_images == 3
    assert report.completed == 3
    assert not report.ready_for_pdf
    assert "cover_review_required" in report.blocked_reasons
    assert "moment_review_required" in report.blocked_reasons
    approved = {job.scene_id for job in jobs if job.scene_id != "premium-cover"}
    ready = audit_premium_batch(
        jobs=jobs, approved_moment_ids=approved, cover_approved=True,
    )
    assert ready.ready_for_pdf
    assert ready.approved == 3
    assert ready.blocked_reasons == ()


@pytest.mark.parametrize("tamper", [
    "missing", "duplicate", "foreign", "stale", "unfinished_approval",
])
def test_premium_batch_fails_closed_on_invalid_jobs(tamper):
    jobs = _batch()
    approved = {job.scene_id for job in jobs if job.scene_id != "premium-cover"}
    if tamper == "missing":
        jobs.pop()
        report = audit_premium_batch(
            jobs=jobs, approved_moment_ids=set(), cover_approved=False,
        )
        assert "missing_illustrations" in report.blocked_reasons
        return
    if tamper == "duplicate":
        jobs.append(jobs[1].model_copy(deep=True))
    elif tamper == "foreign":
        jobs[1].owner_id = 99
    elif tamper == "stale":
        jobs[1].premium_story_fingerprint = "b" * 64
    else:
        jobs[1].status = JobStatus.RUNNING
        jobs[1].lease_token = "a" * 32
        jobs[1].lease_expires_at = datetime.now(UTC)
    with pytest.raises((PermissionError, ValueError)):
        audit_premium_batch(
            jobs=jobs, approved_moment_ids=approved, cover_approved=True,
        )
