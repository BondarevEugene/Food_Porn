"""Creative modes, likeness gate and print production checks."""
import pytest
from pydantic import ValidationError

from app.little_legend.blueprint import (
    BookBlueprint,
    CharacterProfile,
    CreativeControls,
    PublishingControls,
    print_preflight,
    quick_blueprint,
    visual_consistency_check,
)
from app.little_legend.illustration_direction import build_illustration_brief
from app.little_legend.story_graph import build_graph


def test_quick_mode_requires_only_hero():
    blueprint = quick_blueprint("Оля")
    assert blueprint.controls.mode == "quick"
    assert blueprint.characters[0].name == "Оля"
    assert blueprint.publishing.mode == "quick"


def test_director_mode_preserves_detailed_controls():
    blueprint = BookBlueprint(
        controls=CreativeControls(
            mode="director", age=11, tone="epic", riddles=3,
            protected_plot_points=["Героиня спасает лес"],
        ),
        characters=[CharacterProfile(
            name="Оля", appearance="Каштановые волосы",
            visual_identity_notes="Веснушки",
        )],
    )
    assert BookBlueprint.model_validate_json(blueprint.model_dump_json()) == blueprint


def test_child_photo_likeness_requires_consent_and_approval():
    character = CharacterProfile(name="Оля", visual_reference_approved=True)
    blueprint = BookBlueprint(characters=[character])
    report = visual_consistency_check(blueprint)
    assert report["characters"][0]["photo_likeness_ready"] is False
    assert report["photo_processing_enabled"] is False
    character.photo_consent_confirmed = True
    assert visual_consistency_check(blueprint)["characters"][0]["photo_likeness_ready"]


def test_print_preflight_blocks_unfinished_book():
    report = print_preflight(PublishingControls())
    assert report["ready_for_press"] is False
    assert report["proof_only"] is True
    assert len(report["problems"]) >= 3


def test_duplicate_primary_hero_is_rejected():
    with pytest.raises(ValidationError):
        BookBlueprint(characters=[
            CharacterProfile(name="Оля"),
            CharacterProfile(name="Ася"),
        ])


def test_illustration_brief_preserves_character_identity():
    blueprint = quick_blueprint("Оля", age=11)
    blueprint.characters[0].appearance = "Каштановые волосы и зелёные глаза"
    blueprint.characters[0].visual_identity_notes = "Три веснушки на носу"
    scene = build_graph(["Оля нашла говорящую лису"]).nodes[0]
    brief = build_illustration_brief(scene, blueprint, hero="Оля")
    assert "Три веснушки" in brief.prompt
    assert "Каштановые волосы" in brief.prompt
    assert brief.reference_approval_required is True
    assert brief.generation_enabled is False
