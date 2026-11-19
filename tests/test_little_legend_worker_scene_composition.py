"""The real illustration runner forwards scene-specific composition to its provider."""
import pytest

from app.little_legend.illustration_runner import directed_scene_for_provider
from app.little_legend.story_graph import build_graph


def test_scene_composition_reaches_existing_provider_summary():
    graph = build_graph(["Марта входит в сад", "Марта находит звезду"])
    first, second = graph.nodes
    first.illustration_prompt = "Широкий план: Марта открывает серебряную калитку"
    second.illustration_prompt = "Крупный план: Марта держит светящуюся звезду"
    original = first.summary
    directed_first = directed_scene_for_provider(first)
    directed_second = directed_scene_for_provider(second)
    assert "серебряную калитку" in directed_first.summary
    assert "светящуюся звезду" in directed_second.summary
    assert directed_first.summary != directed_second.summary
    assert first.summary == original
    assert directed_first.id == first.id
    assert directed_first.order == first.order


def test_legacy_scene_without_composition_is_unchanged():
    scene = build_graph(["Тихий сад"]).nodes[0]
    assert directed_scene_for_provider(scene) is scene


def test_composition_without_story_context_fails_closed():
    scene = build_graph(["Тихий сад"]).nodes[0]
    scene.summary = ""
    scene.illustration_prompt = "Герой летит"
    with pytest.raises(ValueError, match="no narrative summary"):
        directed_scene_for_provider(scene)


def test_oversized_composition_does_not_silently_truncate():
    scene = build_graph(["С" * 4000]).nodes[0]
    scene.illustration_prompt = "А" * 2000
    with pytest.raises(ValueError, match="oversized"):
        directed_scene_for_provider(scene)
