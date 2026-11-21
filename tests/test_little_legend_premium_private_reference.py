"""Private reference bytes must be sanitized and loaded before paid dispatch."""
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.premium_batch_manifest import PremiumArtRequest
from app.little_legend.premium_private_reference import (
    load_private_premium_reference,
)


class Reader:
    def __init__(self, *, missing=False):
        self.missing = missing
        self.calls = []

    async def read_reference(self, *, owner_id, story_id, reference_id):
        self.calls.append((owner_id, story_id, reference_id))
        if self.missing:
            raise PermissionError("Photo unavailable")
        buffer = BytesIO()
        Image.new("RGB", (80, 80)).save(buffer, format="PNG")
        return buffer.getvalue()


def _request():
    return PremiumArtRequest(
        moment_id="premium-cover", chapter_index=0,
        reference_id="private-photo-1", scene_description="Portrait",
        costume_direction="Royal robe", background_direction="Castle",
        expected_revision=1, estimated_micro_usd=50000,
    )


@pytest.mark.asyncio
async def test_private_photo_is_authorized_and_sanitized_in_memory():
    reader = Reader()
    result = await load_private_premium_reference(
        reader=reader, owner_id=3, story_id=4, request=_request(),
    )
    assert reader.calls == [(3, 4, "private-photo-1")]
    assert result.reference_id == "private-photo-1"
    assert result.image_jpeg.startswith(bytes((255, 216, 255)))


@pytest.mark.asyncio
async def test_missing_photo_fails_closed():
    with pytest.raises(PermissionError, match="Photo unavailable"):
        await load_private_premium_reference(
            reader=Reader(missing=True), owner_id=3, story_id=4,
            request=_request(),
        )


@pytest.mark.asyncio
async def test_invalid_owner_does_not_read_photo():
    reader = Reader()
    with pytest.raises(PermissionError):
        await load_private_premium_reference(
            reader=reader, owner_id=0, story_id=4, request=_request(),
        )
    assert reader.calls == []
