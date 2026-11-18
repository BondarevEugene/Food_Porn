"""Worker checks: consent, revisions, dispatch fence and sanitized persistence."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.little_legend.image_ai_consent import (
    ImageAIConsent, ImageAIDisclosure, accept_image_ai_consent,
)
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.illustration_worker import (
    IllustrationContext, run_illustration_job,
)
from app.little_legend.story_graph import build_graph
from app.little_legend.writer_queue import JobStatus


def _setup():
    disclosure = ImageAIDisclosure(
        provider="OpenAI", legal_entity="OpenAI",
        processing_countries="US", retention_policy="See policy",
        privacy_url="https://openai.com/policies/privacy-policy/",
        enabled=True,
    )
    consent = accept_image_ai_consent(
        provider="OpenAI", notice=disclosure.notice(),
        terms_accepted=True, disclosure=disclosure,
    )
    context = IllustrationContext(
        scene=build_graph(["A forest"]).nodes[0], hero="Marta",
        style="watercolor", consent=consent, disclosure=disclosure,
        current_revision=1, owner_verified=True,
        manuscript_approved=True,
    )
    job = IllustrationJob(
        job_id="lli_test_123456", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="a" * 32,
        lease_expires_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC,
        ) + __import__("datetime").timedelta(minutes=3),
    )
    return job, context


class FakeIllustrator:
    def __init__(self, calls):
        self.calls = calls

    async def generate_scene(self, **kwargs):
        self.calls.append("provider")
        output = BytesIO()
        Image.new("RGB", (600, 600), "white").save(output, format="PNG")
        return output.getvalue()


@pytest.mark.asyncio
async def test_worker_fences_before_provider_and_sanitizes_image():
    job, context = _setup()
    calls = []

    async def fence(_job):
        calls.append("fence")

    async def persist(_job, data):
        assert data.startswith(bytes((255, 216, 255)))
        calls.append("persist")

    async def complete(_job):
        calls.append("complete")

    await run_illustration_job(
        job=job, context=context, illustrator=FakeIllustrator(calls),
        fence_dispatch=fence, persist_image=persist,
        mark_completed=complete,
    )
    assert calls == ["fence", "provider", "persist", "complete"]


@pytest.mark.asyncio
async def test_worker_rejects_revoked_consent_before_dispatch():
    job, context = _setup()
    context = IllustrationContext(
        **{**vars(context), "consent": ImageAIConsent()},
    )
    calls = []

    async def fence(_job):
        calls.append("fence")

    async def persist(_job, _data):
        calls.append("persist")

    async def complete(_job):
        calls.append("complete")

    with pytest.raises(PermissionError, match="consent"):
        await run_illustration_job(
            job=job, context=context, illustrator=FakeIllustrator(calls),
            fence_dispatch=fence, persist_image=persist,
            mark_completed=complete,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_private_store_worker_writes_before_completion():
    job, context = _setup()
    calls = []

    class Store:
        def put(self, *, key, data, content_type):
            assert key.startswith("little-legend/generated/")
            assert data.startswith(bytes((255, 216, 255)))
            assert content_type == "image/jpeg"
            calls.append("store")

    async def fence(_job):
        calls.append("fence")

    async def complete(_job):
        calls.append("complete")

    await run_illustration_job_with_private_store(
        job=job, context=context, illustrator=FakeIllustrator(calls),
        store=Store(), fence_dispatch=fence, mark_completed=complete,
    )
    assert calls == ["fence", "provider", "store", "complete"]
