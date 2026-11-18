"""Character arc is planning guidance, not semantic proof."""
import pytest

from app.little_legend.character_arc import plan_character_arc
from app.little_legend.hero_contract import HeroContract
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import build_graph


def test_arc_preserves_scene_order_and_hero_agency():
    graph = build_graph(["Начало", "Выбор", "Развязка"])
    contract = HeroContract(hero_name="Марта", family_approved=True)
    design = StoryDesign(
        desire="Найти ключ", decisive_choice="Открыть дверь",
        transformation="Научиться просить помощи",
    )
    arc = plan_character_arc(graph, contract, design)
    assert [point.order for point in arc.checkpoints] == [1, 2, 3]
    assert arc.hero_name == "Марта"
    assert arc.missing_anchors == []
    assert arc.semantic_arc_verified is False
    assert arc.family_facts_are_immutable


def test_missing_arc_anchors_are_visible_not_fabricated():
    arc = plan_character_arc(
        build_graph(["Начало"]),
        HeroContract(hero_name="Марта", family_approved=True),
        StoryDesign(),
    )
    assert set(arc.missing_anchors) == {
        "desire", "transformation", "decisive_choice",
    }


def test_unapproved_hero_blocks_arc():
    with pytest.raises(PermissionError, match="Parent-approved"):
        plan_character_arc(
            build_graph(["Начало"]), HeroContract(hero_name="Марта"),
            StoryDesign(),
        )
