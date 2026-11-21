"""Durable premium snapshots survive JSON roundtrips and reject tampering."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_job_context import restore_premium_job_context
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.writer_queue import JobStatus


def _job():
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE, reference_ids=["a", "b", "c"],
        chapter_moments=[("Forest path", "Castle bridge")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=4, story_id=7, plan=plan, chapter_revisions=[2],
    )
    job = IllustrationJob(
        job_id="lli_durable_123456", owner_id=4, story_id=7,
        scene_id="chapter-01-moment-1", expected_revision=2,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="durable-lease-token-123456789",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        premium_manifest_fingerprint=manifest.fingerprint,
        premium_story_fingerprint="a" * 64,
        premium_manifest_snapshot=manifest.model_dump(mode="json"),
        premium_plan_snapshot=plan.model_dump(mode="json"),
    )
    return IllustrationJob.model_validate_json(job.model_dump_json())


def test_restore_durable_premium_job_after_json_roundtrip():
    job = _job()
    context = restore_premium_job_context(job)
    assert context.manifest.requests[1].moment_id == job.scene_id
    assert context.plan.cover_reference_id == "a"


@pytest.mark.parametrize("tamper", [
    "missing", "owner", "prompt", "fingerprint", "cost", "genre",
])
def test_restore_rejects_missing_or_tampered_snapshot(tamper):
    job = _job()
    if tamper == "missing":
        job.premium_plan_snapshot = None
    elif tamper == "owner":
        job.premium_manifest_snapshot["owner_id"] = 999
    elif tamper == "prompt":
        job.premium_manifest_snapshot["requests"][0]["scene_description"] = "Changed"
    elif tamper == "fingerprint":
        job.premium_manifest_fingerprint = "f" * 64
    elif tamper == "cost":
        job.premium_manifest_snapshot["requests"][1]["estimated_micro_usd"] += 1
    else:
        job.premium_plan_snapshot["genre"] = "detective"
    with pytest.raises((PermissionError, ValueError)):
        restore_premium_job_context(job)


def test_legacy_job_has_no_premium_snapshot():
    job = IllustrationJob(
        job_id="lli_legacy_123456", owner_id=4, story_id=7,
        scene_id="scene_1", expected_revision=2, estimated_cost_usd=0.05,
    )
    with pytest.raises(PermissionError):
        restore_premium_job_context(job)
