"""Image receipts never bypass persistence or invent a provider charge."""
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.illustration_worker import IllustrationContext, run_illustration_job
from app.little_legend.image_ai_consent import (
    ImageAIDisclosure,
    accept_image_ai_consent,
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
        current_revision=1, owner_verified=True, manuscript_approved=True,
    )
    job = IllustrationJob(
        job_id="lli_receipt_test", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="a" * 32,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=3),
    )
    return job, context


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (600, 600), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_receipt_optional_when_provider_does_not_supply_reference() -> None:
    result = IllustrationProviderResult(data=_png())
    assert result.actual_micro_usd is None
    assert result.provider_reference is None


@pytest.mark.parametrize(
    ("amount", "reference"),
    [(-1, "img-1"), (True, "img-1"), (100, None), (None, "img-1")],
)
def test_incomplete_receipt_rejected(amount, reference) -> None:
    with pytest.raises(ValueError, match="receipt"):
        IllustrationProviderResult(
            data=_png(), actual_micro_usd=amount,
            provider_reference=reference,
        )


@pytest.mark.asyncio
async def test_receipt_completion_occurs_after_private_persistence() -> None:
    job, context = _setup()
    calls = []

    class Provider:
        async def generate_scene_with_receipt(self, **kwargs):
            calls.append("provider")
            return IllustrationProviderResult(
                data=_png(), actual_micro_usd=300,
                provider_reference="img-123",
            )

    async def fence(_job):
        calls.append("fence")

    async def persist(_job, data):
        assert data.startswith(bytes((255, 216, 255)))
        calls.append("persist")

    async def legacy_complete(_job):
        raise AssertionError("Receipt completion should be used")

    async def complete(_job, receipt):
        assert receipt.actual_micro_usd == 300
        assert receipt.provider_reference == "img-123"
        calls.append("complete")

    await run_illustration_job(
        job=job, context=context, illustrator=Provider(),
        fence_dispatch=fence, persist_image=persist,
        mark_completed=legacy_complete,
        mark_completed_with_receipt=complete,
    )
    assert calls == ["fence", "provider", "persist", "complete"]
