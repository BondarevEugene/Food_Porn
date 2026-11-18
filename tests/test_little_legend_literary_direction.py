"""Literary direction is deterministic and respects approved audience controls."""
from app.little_legend.blueprint import CreativeControls
from app.little_legend.literary_direction import build_literary_direction
from app.little_legend.narrative_design import StoryDesign


def test_young_reader_direction_and_editorial_gate():
    direction = build_literary_direction(
        CreativeControls(age=5, language="uk", reading_level="early"),
        StoryDesign(), mode="quick", scene_goal="Find the key",
        scene_conflict="A locked door",
    )
    assert direction.language == "uk"
    assert direction.audience_age == 5
    assert direction.human_editor_required is True
    assert any("short concrete sentences" in s for s in direction.style_instructions)
    assert any("Find the key" in s for s in direction.scene_requirements)


def test_director_mode_adds_depth_without_inventing_child_facts():
    direction = build_literary_direction(
        CreativeControls(age=11), StoryDesign(theme="friendship"),
        mode="director", scene_goal="", scene_conflict="",
    )
    assert any("subtext" in s for s in direction.scene_requirements)
    assert any("Do not invent personal facts" in s for s in direction.scene_requirements)


def test_unknown_age_is_not_silently_assumed():
    direction = build_literary_direction(
        CreativeControls(), StoryDesign(), mode="quick",
        scene_goal="", scene_conflict="",
    )
    assert direction.audience_age is None
    assert any("Reading age is unknown" in s for s in direction.style_instructions)
