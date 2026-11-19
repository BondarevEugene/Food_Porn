"""Scene art instructions must never disappear through hidden prompt slicing."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.little_legend.illustration_runner import directed_scene_for_provider
from app.little_legend.openai_illustration_provider import (
    IllustrationSettings,
    OpenAIIllustrationProvider,
)
from app.little_legend.story_graph import build_graph


def test_directed_scene_fits_actual_provider_limit():
    scene = build_graph(["Сад"]).nodes[0]
    scene.illustration_prompt = "Крупный план: герой держит звезду"
    result = directed_scene_for_provider(scene)
    assert len(result.summary) <= 2000
    assert "держит звезду" in result.summary


def test_directed_scene_rejects_content_provider_would_truncate():
    scene = build_graph(["С" * 1980]).nodes[0]
    scene.illustration_prompt = "Композиция: герой держит звезду"
    with pytest.raises(ValueError, match="oversized"):
        directed_scene_for_provider(scene)


def test_legacy_scene_rejects_oversized_summary():
    scene = build_graph(["С" * 2001]).nodes[0]
    with pytest.raises(ValueError, match="provider prompt limit"):
        directed_scene_for_provider(scene)


@pytest.mark.asyncio
async def test_provider_rejects_oversized_scene_before_paid_request():
    images = SimpleNamespace(generate=AsyncMock())
    provider = OpenAIIllustrationProvider(
        client=SimpleNamespace(images=images),
        settings=IllustrationSettings(enabled=True),
    )
    scene = build_graph(["С" * 2001]).nodes[0]
    with pytest.raises(ValueError, match="provider prompt limit"):
        await provider.generate_scene_with_receipt(
            scene=scene, hero="Марта", style="watercolor"
        )
    images.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_rejects_oversized_hero_and_style_before_paid_request():
    images = SimpleNamespace(generate=AsyncMock())
    provider = OpenAIIllustrationProvider(
        client=SimpleNamespace(images=images),
        settings=IllustrationSettings(enabled=True),
    )
    scene = build_graph(["Сад"]).nodes[0]
    for hero, style in [("М" * 101, "watercolor"), ("Марта", "s" * 121)]:
        with pytest.raises(ValueError, match="prompt limit"):
            await provider.generate_scene_with_receipt(
                scene=scene, hero=hero, style=style
            )
    images.generate.assert_not_awaited()
