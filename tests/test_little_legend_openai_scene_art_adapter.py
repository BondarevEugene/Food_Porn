"""The production illustration adapter keeps distinct scene actions and identity."""
import asyncio

import pytest

from app.little_legend.art_provider_bridge import (
    ArtGenerationPolicy,
    generate_scene_candidates,
)
from app.little_legend.hero_contract import FactPriority, HeroContract, HeroFact
from app.little_legend.openai_scene_art_adapter import OpenAISceneArtAdapter
from app.little_legend.scene_art_direction import build_scene_art_direction
from app.little_legend.story_graph import build_graph


class FakeExistingProvider:
    def __init__(self):
        self.calls = []

    async def generate_scene(self, *, scene, hero, style, continuity=""):
        self.calls.append((scene, hero, style, continuity))
        return b"test-image"


def _direction():
    graph = build_graph(["Открывает ворота", "Находит звезду"])
    contract = HeroContract(
        hero_name="Марта", family_approved=True,
        facts=[HeroFact(key="appearance", value="зелёные глаза",
                        priority=FactPriority.IMMUTABLE)],
    )
    return build_scene_art_direction(contract, graph)


def test_existing_provider_receives_unique_scenes_and_shared_identity():
    provider = FakeExistingProvider()
    result = asyncio.run(generate_scene_candidates(
        OpenAISceneArtAdapter(provider), _direction(),
        style="watercolor", requested_scene_ids={"scene_1", "scene_2"},
        policy=ArtGenerationPolicy(enabled=True),
    ))
    assert len(result) == 2
    assert "Открывает ворота" in provider.calls[0][0].summary
    assert "Находит звезду" in provider.calls[1][0].summary
    assert "зелёные глаза" in provider.calls[0][3]
    assert provider.calls[0][3] == provider.calls[1][3]
    assert not any(item.human_approved for item in result)


def test_oversized_identity_is_rejected_before_provider_call():
    provider = FakeExistingProvider()
    direction = _direction()
    direction.briefs[0].identity_anchor = ("x" * 1201,)
    with pytest.raises(ValueError, match="continuity"):
        asyncio.run(generate_scene_candidates(
            OpenAISceneArtAdapter(provider), direction,
            style="watercolor", requested_scene_ids={"scene_1"},
            policy=ArtGenerationPolicy(enabled=True),
        ))
    assert provider.calls == []
