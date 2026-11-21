"""Premium jobs cannot enter the legacy paid-image dispatch path."""
import inspect

from app.little_legend.illustration_queue_store import (
    IllustrationJob,
    claim_next_illustration_job,
    enqueue_premium_illustration_jobs,
    fence_illustration_dispatch,
)


def test_premium_metadata_roundtrip():
    job = IllustrationJob(
        job_id="lli_123456789abcdef", owner_id=1, story_id=2,
        scene_id="chapter-01-moment-1", expected_revision=3,
        estimated_cost_usd=0.05,
        premium_manifest_fingerprint="a" * 64,
        premium_story_fingerprint="b" * 64,
    )
    loaded = IllustrationJob.model_validate_json(job.model_dump_json())
    assert loaded.premium_manifest_fingerprint == "a" * 64
    assert loaded.premium_story_fingerprint == "b" * 64


def test_legacy_jobs_keep_optional_premium_fields_empty():
    job = IllustrationJob(
        job_id="lli_123456789abcdef", owner_id=1, story_id=2,
        scene_id="scene_1", expected_revision=3, estimated_cost_usd=0.05,
    )
    assert job.premium_manifest_fingerprint is None


def test_legacy_claim_and_dispatch_have_premium_isolation():
    claim_source = inspect.getsource(claim_next_illustration_job)
    dispatch_source = inspect.getsource(fence_illustration_dispatch)
    assert "if job.premium_manifest_fingerprint is not None:" in claim_source
    assert "if job.premium_manifest_fingerprint is not None:" in dispatch_source


def test_premium_staging_has_transaction_and_story_lock():
    source = inspect.getsource(enqueue_premium_illustration_jobs)
    assert "with_for_update()" in source
    assert "require_premium_batch_ready(" in source
    assert "await session.commit()" in source
