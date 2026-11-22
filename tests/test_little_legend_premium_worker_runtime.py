"""Worker preflight must block paid calls before dispatch when photos are missing."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_photo_consent import (
    PremiumPhotoDisclosure,
    accept_premium_photo_consent,
)
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.premium_worker_runtime import (
    PremiumWorkerDependencies,
    premium_worker_health,
    run_premium_worker_once,
)
from app.little_legend.writer_queue import JobPolicy, JobStatus


class References:
    def __init__(self, *, missing=False):
        self.missing = missing
        self.calls = []

    async def check_access(self, *, owner_id, story_id, reference_ids):
        self.calls.append((owner_id, story_id, reference_ids))
        if self.missing:
            raise PermissionError("Missing private reference")


def _job():
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE,
        reference_ids=["ref-1", "ref-2", "ref-3"],
        chapter_moments=[("The hidden bridge", "The river crossing")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=1, story_id=2, plan=plan, chapter_revisions=[3],
    )
    return IllustrationJob(
        job_id="lli_worker_123456789", owner_id=1, story_id=2,
        scene_id="premium-cover", expected_revision=3,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="lease-token-123456789",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        premium_manifest_fingerprint=manifest.fingerprint,
        premium_story_fingerprint="a" * 64,
        premium_manifest_snapshot=manifest.model_dump(mode="json"),
        premium_plan_snapshot=plan.model_dump(mode="json"),
    )


class PhotoConsents:
    async def get_photo_consent(self, *, owner_id, story_id):
        disclosure = PremiumPhotoDisclosure(
            provider="OpenAI", legal_entity="OpenAI",
            processing_countries="US", retention_policy="7 days",
            privacy_url="https://example.com/privacy", enabled=True,
        )
        return accept_premium_photo_consent(
            provider=disclosure.provider, notice=disclosure.notice(),
            parent_authorized=True, disclosure=disclosure,
        )


@pytest.fixture(autouse=True)
def photo_disclosure(monkeypatch):
    import app.little_legend.premium_worker_runtime as runtime

    monkeypatch.setattr(
        runtime, "configured_premium_photo_disclosure",
        lambda: PremiumPhotoDisclosure(
            provider="OpenAI", legal_entity="OpenAI",
            processing_countries="US", retention_policy="7 days",
            privacy_url="https://example.com/privacy", enabled=True,
        ),
    )


def _deps(references, *, ready=True):
    return PremiumWorkerDependencies(
        provider=object(), store=object(), references=references,
        reference_reader=object(), photo_consents=PhotoConsents(),
        policy=JobPolicy(), provider_configured=ready,
        private_storage_configured=ready, price_configured=ready,
    )


@pytest.mark.asyncio
async def test_unconfigured_worker_does_not_claim_any_job():
    calls = []

    async def claim(**kwargs):
        calls.append("claim")
        return _job()

    with pytest.raises(RuntimeError, match="must be configured"):
        await run_premium_worker_once(
            dependencies=_deps(References(), ready=False), claim=claim,
        )
    assert calls == []
    assert not premium_worker_health(
        dependencies=_deps(References(), ready=False)
    )["ready"]


@pytest.mark.asyncio
async def test_missing_private_reference_blocks_provider_fence(monkeypatch):
    import app.little_legend.premium_worker_runtime as runtime

    job = _job()
    calls = []

    async def claim(**kwargs):
        calls.append("claim")
        return job

    async def runner(**kwargs):
        calls.append("paid")
        raise AssertionError("Paid provider must never run")

    monkeypatch.setattr(runtime, "run_restored_premium_image_job", runner)

    async def recovery(**kwargs):
        calls.append("recovery")

    import app.little_legend.premium_recovery as recovery_module

    monkeypatch.setattr(recovery_module, "record_premium_pre_dispatch_failure", recovery)
    references = References(missing=True)
    with pytest.raises(PermissionError, match="Missing private reference"):
        await run_premium_worker_once(
            dependencies=_deps(references), claim=claim,
        )
    assert calls == ["claim", "recovery"]
    assert references.calls == [(1, 2, {"ref-1", "ref-2"})]


@pytest.mark.asyncio
async def test_ready_worker_checks_all_references_before_running(monkeypatch):
    import app.little_legend.premium_worker_runtime as runtime

    job = _job()
    calls = []

    async def claim(**kwargs):
        calls.append("claim")
        return job

    async def runner(**kwargs):
        calls.append("runner")
        assert kwargs["job"] is job
        return "little-legend/generated/private.jpg"

    monkeypatch.setattr(runtime, "run_restored_premium_image_job", runner)
    references = References()
    assert await run_premium_worker_once(
        dependencies=_deps(references), claim=claim,
    )
    assert calls == ["claim", "runner"]
    assert references.calls[0][2] == {"ref-1", "ref-2"}


@pytest.mark.asyncio
async def test_empty_queue_does_not_access_photos():
    references = References()

    async def claim(**kwargs):
        return None

    assert not await run_premium_worker_once(
        dependencies=_deps(references), claim=claim,
    )
    assert references.calls == []
