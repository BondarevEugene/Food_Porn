"""Book art direction is deterministic, varied and aligned to provider limits."""
import pytest

from app.little_legend.book_art_director import (
    directed_scene_from_plan,
    plan_book_shots,
)
from app.little_legend.story_graph import build_graph


def test_full_book_has_distinct_camera_language_and_print_safe_area():
    graph = build_graph([f"Сцена приключения {i}" for i in range(12)])
    plan = plan_book_shots(graph)
    assert len(plan.shots) == 12
    assert len({shot.shot for shot in plan.shots}) >= 3
    assert all("gutter" in shot.prompt for shot in plan.shots)
    assert all("trim" in shot.prompt for shot in plan.shots)
    assert all("Atmosphere:" in shot.prompt for shot in plan.shots)
    assert not plan.images_generated
    assert not plan.photo_likeness_verified


def test_plan_is_repeatable_and_does_not_mutate_story():
    graph = build_graph(["Сад", "Тайна", "Разгадка"])
    before = graph.model_dump_json()
    first = plan_book_shots(graph)
    second = plan_book_shots(graph)
    assert first == second
    assert graph.model_dump_json() == before


def test_duplicate_actions_are_flagged_for_editor():
    graph = build_graph(["Сад", "Тайна", "Разгадка"])
    graph.nodes[0].illustration_prompt = "Одинаковый кадр"
    graph.nodes[2].illustration_prompt = "  одинаковый   кадр "
    plan = plan_book_shots(graph)
    assert "Duplicate visual action across chapters" in plan.shots[0].warnings
    assert "Duplicate visual action across chapters" in plan.shots[2].warnings


def test_directed_scene_keeps_original_unchanged():
    graph = build_graph(["Марта входит в замок"])
    original = graph.nodes[0].summary
    shot = plan_book_shots(graph).shots[0]
    directed = directed_scene_from_plan(graph.nodes[0], shot)
    assert directed.summary == shot.prompt
    assert graph.nodes[0].summary == original


def test_wrong_scene_cannot_receive_another_scenes_direction():
    graph = build_graph(["Первая", "Вторая"])
    with pytest.raises(ValueError, match="does not match"):
        directed_scene_from_plan(graph.nodes[1], plan_book_shots(graph).shots[0])


def test_oversized_prompt_is_blocked_before_paid_generation():
    graph = build_graph(["С" * 1980])
    with pytest.raises(ValueError, match="provider prompt limit"):
        plan_book_shots(graph)


def test_empty_scene_is_blocked():
    graph = build_graph(["Первая"])
    graph.nodes[0].summary = ""
    with pytest.raises(ValueError, match="lacks story context"):
        plan_book_shots(graph)
