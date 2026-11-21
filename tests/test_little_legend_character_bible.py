"""Approved visual identity must remain identical in every scene brief."""
import pytest

from app.little_legend.blueprint import (
    BookBlueprint,
    CharacterProfile,
    CreativeControls,
)
from app.little_legend.character_bible import (
    audit_scene_art_briefs,
    build_character_bible,
    scene_art_briefs,
)
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.story_graph import build_graph


def _approved():
    blueprint = BookBlueprint(
        controls=CreativeControls(illustration_style="watercolor", language="uk"),
        characters=[
            CharacterProfile(
                name="Оля", role="hero",
                appearance="Кучеряве волосся", visual_identity_notes="Синій шарф",
            ),
            CharacterProfile(name="Лис", role="friend", appearance="Рудий"),
        ],
        family_approved=True,
    )
    return blueprint, contract_from_blueprint(blueprint, "Оля")


def test_approved_character_bible_is_repeatable_and_scene_stable():
    blueprint, contract = _approved()
    bible = build_character_bible(blueprint, contract)
    assert bible.fingerprint == build_character_bible(blueprint, contract).fingerprint
    briefs = scene_art_briefs(build_graph(["Ліс", "Дім"]), bible)
    assert [b.scene_id for b in briefs] == ["scene_1", "scene_2"]
    assert all(b.style == "watercolor" and b.language == "uk" for b in briefs)
    assert all(b.characters == bible.characters for b in briefs)
    assert not audit_scene_art_briefs(briefs, bible)


def test_unauthorized_character_profile_is_rejected():
    blueprint, contract = _approved()
    blueprint.family_approved = False
    with pytest.raises(PermissionError):
        build_character_bible(blueprint, contract)


def test_hero_identity_mismatch_is_rejected():
    blueprint, contract = _approved()
    blueprint.characters[0].name = "Інша"
    with pytest.raises(ValueError):
        build_character_bible(blueprint, contract)


def test_character_changes_invalidate_fingerprint_and_briefs():
    blueprint, contract = _approved()
    old = build_character_bible(blueprint, contract)
    briefs = scene_art_briefs(build_graph(["Ліс"]), old)
    blueprint.characters[0].visual_identity_notes = "Зелений шарф"
    updated = build_character_bible(blueprint, contract)
    assert updated.fingerprint != old.fingerprint
    assert audit_scene_art_briefs(briefs, updated)


def test_mutated_scene_identity_is_detected():
    blueprint, contract = _approved()
    bible = build_character_bible(blueprint, contract)
    briefs = scene_art_briefs(build_graph(["Ліс"]), bible)
    briefs[0].characters[0].appearance = "Невідома зовнішність"
    assert "scene_1:character_identity_mismatch" in audit_scene_art_briefs(
        briefs, bible,
    )
