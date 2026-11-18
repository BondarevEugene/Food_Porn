"""Story memory must preserve order and never leak future manuscript prose."""
import pytest

from app.little_legend.story_graph import build_graph
from app.little_legend.story_memory import build_story_memory
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_memory_tracks_past_and_future_without_future_prose():
    graph = build_graph(["Первое событие", "Второе событие", "Развязка"])
    graph.nodes[0].consequence = "Ключ найден"
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[
            ChapterDraft(scene_id="scene_1", text="Марта нашла ключ."),
            ChapterDraft(scene_id="scene_3", text="СЕКРЕТНАЯ РАЗВЯЗКА"),
        ],
    )
    memory = build_story_memory(graph, scene_id="scene_2", manuscript=manuscript)
    assert memory.established_events[0].causal_consequence == "Ключ найден"
    assert memory.upcoming_obligations[0].scene_id == "scene_3"
    assert memory.prior_prose_excerpts == [
        {"scene_id": "scene_1", "text": "Марта нашла ключ."}
    ]
    assert "СЕКРЕТНАЯ РАЗВЯЗКА" not in memory.model_dump_json()
    assert memory.semantic_fidelity_verified is False


def test_memory_refuses_unknown_scene():
    with pytest.raises(ValueError, match="Unknown scene"):
        build_story_memory(build_graph(["Начало"]), scene_id="missing")


def test_memory_bounds_previous_prose():
    graph = build_graph(["Первое", "Второе"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="А" * 2000)],
    )
    memory = build_story_memory(
        graph, scene_id="scene_2", manuscript=manuscript, excerpt_chars=100,
    )
    assert len(memory.prior_prose_excerpts[0]["text"]) == 100
