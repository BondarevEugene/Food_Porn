"""Image receipts never bypass persistence or invent a provider charge."""
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.illustration_worker import run_illustration_job
from tests.test_little_legend_illustration_worker import _setup


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
