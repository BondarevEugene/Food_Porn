"""Approved identity notes flow into the real text-only art contract."""
import pytest

from app.little_legend.blueprint import BookBlueprint, CharacterProfile
from app.little_legend.character_identity import IdentityBible, VisualIdentity
from app.little_legend.reviewed_identity_prompt import reviewed_identity_continuity


def book():
    return BookBlueprint(characters=[
        CharacterProfile(name="Марта", role="hero", appearance="Рыжие волосы"),
    ])


def bible(**kwargs):
    return IdentityBible(hero_name="Марта", identity=VisualIdentity(**kwargs))


def contract(blueprint=None, identity_bible=None):
    return reviewed_identity_continuity(
        blueprint=blueprint, bible=identity_bible, hero_name="Марта",
    )


def test_reviewed_anchors_are_used_across_scenes():
    notes = bible(
        parent_reviewed_description=True, hair="Кудри", eyes="Зелёные",
        face="Веснушки", proportions="Невысокая",
        distinctive_features=["Родинка на щеке"],
        forbidden_changes=["Не менять цвет глаз"],
    )
    result = contract(book(), notes)
    for fragment in ["Рыжие волосы", "Кудри", "Зелёные", "Веснушки",
                     "Невысокая", "Родинка на щеке", "Не менять цвет глаз"]:
        assert fragment in result
    assert result == contract(book(), notes)


def test_unreviewed_identity_never_leaks_to_provider():
    notes = bible(hair="Неутверждённая деталь")
    result = contract(book(), notes)
    assert "Рыжие волосы" in result
    assert "Неутверждённая деталь" not in result


def test_identity_from_different_hero_is_rejected():
    notes = IdentityBible(
        hero_name="Олег",
        identity=VisualIdentity(parent_reviewed_description=True, hair="Русые"),
    )
    with pytest.raises(PermissionError, match="another hero"):
        contract(book(), notes)


def test_conflicting_blueprint_hero_is_rejected():
    blueprint = BookBlueprint(characters=[
        CharacterProfile(name="Олег", role="hero", appearance="Русые"),
    ])
    with pytest.raises(PermissionError, match="conflicts"):
        contract(blueprint, bible(parent_reviewed_description=True, hair="Рыжие"))


def test_oversized_approved_notes_fail_closed():
    notes = bible(parent_reviewed_description=True, face="А" * 300,
                  proportions="Б" * 300, clothing_signature="В" * 300,
                  hair="Г" * 200, eyes="Д" * 200)
    with pytest.raises(ValueError, match="continuity limit"):
        contract(book(), notes)


def test_no_approved_identity_preserves_legacy_book_behavior():
    assert contract(book()) == contract(book(), bible())
    assert contract(None, None) == ""
