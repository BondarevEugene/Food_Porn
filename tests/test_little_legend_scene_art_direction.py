"""Scene art direction preserves identity and changes scene-specific action."""
import pytest

from app.little_legend.hero_contract import (
    FactPriority,
    HeroContract,
    HeroFact,
)
from app.little_legend.scene_art_direction import (
    art_direction_report,
    build_scene_art_direction,
)
from app.little_legend.story_graph import build_graph


def _contract(approved: bool = True) -> HeroContract:
    return HeroContract(
        hero_name="Марта",
        family_approved=approved,
        facts=[
            HeroFact(key="name", value="Марта", priority=FactPriority.IMMUTABLE),
            HeroFact(
                key="appearance",
                value="каштановые волосы, зелёные глаза",
                priority=FactPriority.IMMUTABLE,
            ),
            HeroFact(
                key="favorite_phrases",
                value="Я попробую!",
                priority=FactPriority.IMPORTANT,
            ),
        ],
        forbidden_inventions=["Не изменять цвет глаз"],
    )


def test_each_scene_gets_distinct_action_and_same_hero_identity() -> None:
    graph = build_graph(["Марта открывает ворота", "Марта находит звезду"])
    graph.nodes[0].illustration_prompt = "Марта открывает серебряные ворота"
    graph.nodes[1].illustration_prompt = "Марта держит звезду в ладонях"
    direction = build_scene_art_direction(_contract(), graph)
    first, second = direction.briefs
    assert first.scene_action != second.scene_action
    assert first.identity_anchor == second.identity_anchor
    assert "каштановые волосы, зелёные глаза" in first.identity_anchor[1]
    assert "favorite_phrases" not in repr(first.identity_anchor)
    assert first.forbidden_inventions == ("Не изменять цвет глаз",)
    assert first.review_required and not first.generated
    report = art_direction_report(direction, graph)
    assert report["missing_scenes"] == []
    assert not report["identity_consistency_verified"]
    assert not report["images_generated"]


def test_art_direction_requires_parent_approval() -> None:
    with pytest.raises(PermissionError):
        build_scene_art_direction(_contract(approved=False), build_graph(["Сад"]))


def test_art_direction_rejects_empty_scene_description() -> None:
    with pytest.raises(ValueError, match="visual narrative summary"):
        build_scene_art_direction(_contract(), build_graph([" "]))
