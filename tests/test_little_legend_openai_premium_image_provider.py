"""OpenAI premium image adapter sends an actual photo and handles receipts."""
import base64

import pytest

from app.little_legend.openai_premium_image_provider import (
    OpenAIPremiumImageProvider,
    OpenAIPremiumImageSettings,
)
from app.little_legend.premium_batch_manifest import PremiumArtRequest
from app.little_legend.premium_private_reference import PrivatePremiumReference
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan


def _request():
    return PremiumArtRequest(
        moment_id="premium-cover", chapter_index=0,
        reference_id="photo-1", scene_description="Magical forest",
        costume_direction="Green cloak", background_direction="Ancient trees",
        expected_revision=1, estimated_micro_usd=50000,
    )


def _plan():
    return build_visual_plan(
        genre=BookGenre.FAIRY_TALE,
        reference_ids=["photo-1", "photo-2"],
        chapter_moments=[("Forest", "Castle")],
    )


@pytest.mark.asyncio
async def test_provider_uses_photo_in_multipart_request(monkeypatch):
    from app.little_legend import openai_premium_image_provider as module

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [{
                    "b64_json": base64.b64encode(b"image-result").decode(),
                }],
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, data, files):
            calls.append((url, headers, data, files))
            return Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    provider = OpenAIPremiumImageProvider(
        OpenAIPremiumImageSettings(api_key="test-key"),
    )
    result = await provider.generate_premium_image(
        request=_request(), plan=_plan(),
        reference=PrivatePremiumReference(
            reference_id="photo-1", image_jpeg=bytes((255, 216, 255, 1)),
        ),
    )
    assert result.image == b"image-result"
    assert calls[0][0].endswith("/images/edits")
    assert calls[0][3]["image"][1].startswith(bytes((255, 216, 255)))
    assert "Magical forest" in calls[0][2]["prompt"]


@pytest.mark.asyncio
async def test_provider_blocks_wrong_photo_without_http():
    provider = OpenAIPremiumImageProvider(
        OpenAIPremiumImageSettings(api_key="test-key"),
    )
    with pytest.raises(PermissionError):
        await provider.generate_premium_image(
            request=_request(), plan=_plan(),
            reference=PrivatePremiumReference(
                reference_id="wrong", image_jpeg=bytes((255, 216, 255)),
            ),
        )
