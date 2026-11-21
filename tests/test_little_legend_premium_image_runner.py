"""Premium runner tests: paid dispatch ordering, private storage, no retries."""
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.generated_art_store import illustration_key
from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_image_runner import run_premium_image_job
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.writer_queue import JobPolicy, JobStatus


def setup():
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE, reference_ids=["photo-a", "photo-b", "photo-c"],
        chapter_moments=[("Forest meeting", "Castle gates")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=1, story_id=2, plan=plan, chapter_revisions=[3],
    )
    job = IllustrationJob(
        job_id="lli_123456789abcdef", owner_id=1, story_id=2,
        scene_id="chapter-01-moment-1", expected_revision=3,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="valid-lease-token-123456",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        premium_manifest_fingerprint=manifest.fingerprint,
        premium_story_fingerprint="b" * 64,
    )
    return plan, manifest, job


class ReferenceReader:
    async def read_reference(self, *, owner_id, story_id, reference_id):
        image = BytesIO()
        Image.new("RGB", (100, 100)).save(image, format="PNG")
        return image.getvalue()


class Store:
    def __init__(self, events):
        self.events = events
        self.saved = {}

    def put(self, *, key, data, content_type):
        self.events.append("store")
        self.saved[key] = data
        assert content_type == "image/jpeg"


class Provider:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail

    async def generate_premium_image(self, *, request, plan, reference):
        assert reference.reference_id == request.reference_id
        assert reference.image_jpeg.startswith(bytes((255, 216, 255)))
        self.events.append("provider")
        assert request.moment_id == "chapter-01-moment-1"
        if self.fail:
            raise RuntimeError("ambiguous provider failure")
        image = BytesIO()
        Image.new("RGB", (100, 100)).save(image, format="PNG")
        return IllustrationProviderResult(
            image=image.getvalue(), actual_micro_usd=50000,
            provider_reference="provider-123",
        )


@pytest.mark.asyncio
async def test_runner_fences_before_paid_call_and_stores_private_jpeg():
    plan, manifest, job = setup()
    events = []
    store = Store(events)

    async def fence_dispatch(**kwargs):
        events.append("fence")
        assert kwargs["token"] == job.lease_token
        return job.model_copy(update={"provider_dispatched_at": datetime.now(UTC)})

    async def complete_job(**kwargs):
        events.append("complete")
        assert kwargs["policy"].max_attempts == 3
        assert kwargs["provider_reference"] == "provider-123"
        return job.model_copy(update={"status": JobStatus.COMPLETED})

    key = await run_premium_image_job(
        job=job, manifest=manifest, plan=plan, provider=Provider(events),
        reference_reader=ReferenceReader(), store=store, policy=JobPolicy(),
        fence_dispatch=fence_dispatch, complete_job=complete_job,
    )
    assert events == ["fence", "provider", "store", "complete"]
    assert key == illustration_key(owner_id=1, story_id=2, job_id=job.job_id)
    assert store.saved[key].startswith(bytes((255, 216, 255)))


@pytest.mark.asyncio
async def test_ambiguous_provider_failure_never_marks_completed_or_retries():
    plan, manifest, job = setup()
    events = []

    async def fence_dispatch(**kwargs):
        events.append("fence")
        return job.model_copy(update={"provider_dispatched_at": datetime.now(UTC)})

    async def complete_job(**kwargs):
        events.append("complete")
        return job

    with pytest.raises(RuntimeError, match="ambiguous"):
        await run_premium_image_job(
            job=job, manifest=manifest, plan=plan,
            provider=Provider(events, fail=True),
            reference_reader=ReferenceReader(), store=Store(events),
            policy=JobPolicy(), fence_dispatch=fence_dispatch,
            complete_job=complete_job,
        )
    assert events == ["fence", "provider"]


@pytest.mark.asyncio
async def test_invalid_lease_never_dispatches_paid_provider():
    plan, manifest, job = setup()
    job = job.model_copy(update={"provider_dispatched_at": datetime.now(UTC)})
    events = []

    async def forbidden(**kwargs):
        events.append("forbidden")
        raise AssertionError("Should not be called")

    with pytest.raises(PermissionError):
        await run_premium_image_job(
            job=job, manifest=manifest, plan=plan, provider=Provider(events),
            reference_reader=ReferenceReader(),
            store=Store(events), policy=JobPolicy(),
            fence_dispatch=forbidden, complete_job=forbidden,
        )
    assert events == []
