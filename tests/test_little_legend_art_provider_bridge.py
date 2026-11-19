"""The art bridge never bypasses review, budgets or explicit provider enablement."""
import asyncio

import pytest

from app.little_legend.art_provider_bridge import (
    ArtGenerationPolicy,
    generate_scene_candidates,
    scene_art_prompt,
)
from app.little_legend.hero_contract import FactPriority, HeroContract, HeroFact
from app.little_legend.scene_art_direction import build_scene_art_direction
from app.little_legend.story_graph import build_graph


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_scene(self, prompt: dict) -> bytes:
        self.calls.append(prompt)
        return b"test-image"


def _direction():
    graph = build_graph(["Марта у ворот", "Марта в звёздном саду"])
    contract = HeroContract(
        hero_name="Марта", family_approved=True,
        facts=[HeroFact(key="appearance", value="зелёные глаза",
                        priority=FactPriority.IMMUTABLE)],
    )
    return build_scene_art_direction(contract, graph)


def test_prompt_preserves_identity_and_specific_scene() -> None:
    direction = _direction()
    first, second = direction.briefs
    a = scene_art_prompt(first, style="watercolor")
    b = scene_art_prompt(second, style="watercolor")
    assert a["identity_anchor"] == b["identity_anchor"]
    assert a["scene_action"] != b["scene_action"]
    assert a["parent_review_required"] is True


def test_disabled_policy_makes_no_provider_calls() -> None:
    provider = FakeProvider()
    with pytest.raises(PermissionError):
        asyncio.run(generate_scene_candidates(
            provider, _direction(), style="watercolor",
            requested_scene_ids={"scene_1"},
            policy=ArtGenerationPolicy(),
        ))
    assert provider.calls == []


def test_generated_images_are_candidates_not_approved() -> None:
    provider = FakeProvider()
    results = asyncio.run(generate_scene_candidates(
        provider, _direction(), style="watercolor",
        requested_scene_ids={"scene_2", "scene_1"},
        policy=ArtGenerationPolicy(enabled=True),
    ))
    assert [r.scene_id for r in results] == ["scene_1", "scene_2"]
    assert not any(r.human_approved or r.identity_verified for r in results)
    assert provider.calls[0]["identity_anchor"] == provider.calls[1]["identity_anchor"]


def test_unknown_scene_or_bad_style_never_calls_provider() -> None:
    provider = FakeProvider()
    for ids, style in [({"missing"}, "watercolor"), ({"scene_1"}, "")]:
        with pytest.raises(ValueError):
            asyncio.run(generate_scene_candidates(
                provider, _direction(), style=style,
                requested_scene_ids=ids,
                policy=ArtGenerationPolicy(enabled=True),
            ))
    assert provider.calls == []


def test_maximum_scene_limit_blocks_request() -> None:
    provider = FakeProvider()
    with pytest.raises(ValueError, match="Too many"):
        asyncio.run(generate_scene_candidates(
            provider, _direction(), style="watercolor",
            requested_scene_ids={"scene_1", "scene_2"},
            policy=ArtGenerationPolicy(enabled=True, max_scenes_per_request=1),
        ))
    assert provider.calls == []
