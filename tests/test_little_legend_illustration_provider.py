"""Provider contract tests: disabled by default, text-only and bounded images."""
import base64
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.little_legend.openai_illustration_provider import (
    IllustrationSettings,
    OpenAIIllustrationProvider,
)
from app.little_legend.story_graph import build_graph


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (600, 600), "white").save(stream, format="PNG")
    return stream.getvalue()


class FakeImages:
    def __init__(self, encoded):
        self.encoded = encoded
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.encoded)])


def test_provider_requires_explicit_opt_in():
    with pytest.raises(PermissionError, match="disabled"):
        OpenAIIllustrationProvider(
            client=SimpleNamespace(), settings=IllustrationSettings(),
        )


@pytest.mark.asyncio
async def test_provider_generates_text_only_image():
    images = FakeImages(base64.b64encode(_png()).decode("ascii"))
    provider = OpenAIIllustrationProvider(
        client=SimpleNamespace(images=images),
        settings=IllustrationSettings(enabled=True),
    )
    result = await provider.generate_scene(
        scene=build_graph(["A hidden garden"]).nodes[0],
        hero="Marta", style="watercolor", continuity="Red scarf",
    )
    assert result.startswith(b"\\x89PNG")
    assert images.calls[0]["n"] == 1
    assert "image" not in images.calls[0]
    assert "Marta" in images.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_provider_rejects_bad_image_payload():
    provider = OpenAIIllustrationProvider(
        client=SimpleNamespace(images=FakeImages("not base64")),
        settings=IllustrationSettings(enabled=True),
    )
    with pytest.raises(ValueError, match="base64"):
        await provider.generate_scene(
            scene=build_graph(["A hidden garden"]).nodes[0],
            hero="Marta", style="storybook",
        )


def test_provider_rejects_unsupported_size():
    with pytest.raises(ValueError, match="size"):
        IllustrationSettings(enabled=True, size="256x256")
