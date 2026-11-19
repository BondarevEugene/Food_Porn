"""The production art worker must preserve a single fictional hero identity."""
import pytest

from app.little_legend.blueprint import BookBlueprint, CharacterProfile
from app.little_legend.illustration_runner import production_character_continuity


def test_hero_identity_is_explicit_and_stable_across_chapters():
    blueprint = BookBlueprint(characters=[
        CharacterProfile(
            name="Марта", role="hero", appearance="Рыжие кудрявые волосы",
            visual_identity_notes="Веснушки и синий шарф",
        ),
    ])
    first = production_character_continuity(blueprint)
    second = production_character_continuity(blueprint)
    assert first == second
    assert "Рыжие кудрявые волосы" in first
    assert "Веснушки и синий шарф" in first
    assert "same facial features" in first
    assert "never invent new permanent physical traits" in first


def test_other_characters_cannot_override_primary_hero_identity():
    blueprint = BookBlueprint(characters=[
        CharacterProfile(name="Марта", role="hero", appearance="Рыжие волосы"),
        CharacterProfile(name="Друг", role="friend", appearance="Зелёные волосы"),
    ])
    contract = production_character_continuity(blueprint)
    assert "Рыжие волосы" in contract
    assert "Зелёные волосы" not in contract


def test_no_parent_supplied_identity_does_not_invent_one():
    assert production_character_continuity(None) == ""
    assert production_character_continuity(BookBlueprint()) == ""
    assert production_character_continuity(BookBlueprint(
        characters=[CharacterProfile(name="Марта")]
    )) == ""


def test_oversized_identity_fails_before_paid_generation():
    blueprint = BookBlueprint(characters=[
        CharacterProfile(
            name="Марта", role="hero", appearance="А" * 1200,
            visual_identity_notes="Б" * 1200,
        ),
    ])
    with pytest.raises(ValueError, match="continuity exceeds provider limit"):
        production_character_continuity(blueprint)


def test_visual_identity_is_not_treated_as_photo_approval():
    blueprint = BookBlueprint(characters=[
        CharacterProfile(
            name="Марта", role="hero", appearance="Короткие волосы",
            photo_consent_confirmed=False, visual_reference_approved=False,
        ),
    ])
    assert "Короткие волосы" in production_character_continuity(blueprint)
    assert not blueprint.characters[0].visual_reference_approved
