"""Hero-first narrative contract tests."""
import pytest

from app.little_legend.blueprint import (
    BookBlueprint,
    CharacterProfile,
    CreativeControls,
)
from app.little_legend.hero_contract import (
    FactPriority,
    HeroContract,
    HeroFact,
    audit_hero_presence,
    contract_from_blueprint,
    hero_writing_brief,
    scene_directives,
)
from app.little_legend.story_graph import build_graph


def _blueprint():
    return BookBlueprint(
        controls=CreativeControls(age=7, language="uk"),
        characters=[
            CharacterProfile(
                name="Марта", appearance="рыжие кудри",
                mannerisms="прыгает от радости",
                favorite_phrases="У нас получится!",
                relationship="старшая сестра Лизы",
                visual_identity_notes="веснушки",
            ),
        ],
        family_approved=True,
    )


def test_original_details_preserved_without_invention():
    contract = contract_from_blueprint(_blueprint(), "Марта")
    values = {fact.key: fact.value for fact in contract.facts}
    assert values["appearance"] == "рыжие кудри"
    assert values["favorite_phrases"] == "У нас получится!"
    assert values["relationship"] == "старшая сестра Лизы"
    assert values["age"] == "7"
    assert contract.family_approved


def test_hero_name_mismatch_fails_closed():
    with pytest.raises(ValueError):
        contract_from_blueprint(_blueprint(), "Оля")


def test_facts_propagate_to_every_scene():
    contract = contract_from_blueprint(_blueprint(), "Марта")
    directives = scene_directives(contract, build_graph(["Начало", "Финал"]))
    assert len(directives) == 2
    assert all(item["hero"] == "Марта" for item in directives)
    assert all(
        any(fact["key"] == "appearance" for fact in item["immutable_facts"])
        for item in directives
    )


def test_writing_brief_contains_real_hero_and_age():
    brief = hero_writing_brief(
        contract_from_blueprint(_blueprint(), "Марта"), _blueprint()
    )
    assert brief["hero"]["hero_name"] == "Марта"
    assert brief["age"] == 7
    assert brief["language"] == "uk"
    assert brief["remote_generation_performed"] is False


def test_audit_never_claims_fidelity_from_name_mention():
    contract = contract_from_blueprint(_blueprint(), "Марта")
    graph = build_graph(["Начало", "Финал"])
    result = audit_hero_presence(
        contract, {"scene_1": "Марта открыла дверь."}, graph
    )
    assert result["missing_text"] == ["scene_2"]
    assert result["character_fidelity_verified"] is False
    assert result["ready_for_publication"] is False


def test_duplicate_fact_keys_are_rejected():
    with pytest.raises(ValueError):
        HeroContract(
            hero_name="Марта",
            facts=[
                HeroFact(key="name", value="Марта", priority=FactPriority.IMMUTABLE),
                HeroFact(key="name", value="Оля"),
            ],
        )
