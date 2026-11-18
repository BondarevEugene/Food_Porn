"""Narrative depth and premium studio regressions."""
from app.little_legend.blueprint import quick_blueprint
from app.little_legend.narrative_design import StoryDesign, design_guidance
from app.little_legend.router import STUDIO_HTML, StoryDraft
from app.little_legend.story_graph import build_graph


def test_narrative_coaching_is_age_aware_and_non_generative():
    graph = build_graph(["Начало", "Загадка", "Выбор"])
    result = design_guidance(graph, StoryDesign(), quick_blueprint("Оля", age=7))
    assert result["ai_generated"] is False
    assert len(result["scene_advice"]) == 3
    assert len(result["missing_arc_elements"]) == 5
    assert "загадки" in result["audience_guidance"]


def test_story_design_survives_json_roundtrip():
    draft = StoryDraft(design=StoryDesign(
        desire="Спасти лес", need="Научиться просить о помощи",
        decisive_choice="Вернуться за другом",
    ))
    restored = StoryDraft.model_validate_json(draft.model_dump_json())
    assert restored.design.desire == "Спасти лес"
    assert restored.design.decisive_choice == "Вернуться за другом"


def test_premium_studio_has_quick_and_detailed_story_modes():
    assert "Душа вашей истории" in STUDIO_HTML
    assert "openDesign()" in STUDIO_HTML
    assert "designMode()" in STUDIO_HTML
    assert "innerHTML" not in STUDIO_HTML
