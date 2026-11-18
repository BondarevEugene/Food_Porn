"""Storyboard planning is source-grounded and does not generate images."""
import pytest

from app.little_legend.blueprint import quick_blueprint
from app.little_legend.character_identity import quick_identity_bible
from app.little_legend.illustration_storyboard import build_illustration_storyboard
from app.little_legend.story_graph import build_graph


def test_storyboard_has_ordered_scenes_and_stable_identity():
    blueprint = quick_blueprint("Марта")
    blueprint.family_approved = True
    blueprint.characters[0].appearance = "Рыжие волосы"
    identity = quick_identity_bible(blueprint, "Марта")
    graph = build_graph(["Начало", "Испытание", "Развязка"])
    storyboard = build_illustration_storyboard(graph, blueprint, identity)
    assert [shot.chapter for shot in storyboard.shots] == [1, 2, 3]
    assert all("Рыжие волосы" in shot.continuity_anchors for shot in storyboard.shots)
    assert all(shot.approval_status == "draft" for shot in storyboard.shots)
    assert not storyboard.remote_generation_performed
    assert not storyboard.photo_likeness_verified


def test_storyboard_requires_family_approval():
    blueprint = quick_blueprint("Марта")
    with pytest.raises(PermissionError, match="Family"):
        build_illustration_storyboard(
            build_graph(["Начало"]),
            blueprint,
            quick_identity_bible(blueprint, "Марта"),
        )


def test_storyboard_rejects_identity_mismatch():
    blueprint = quick_blueprint("Марта")
    blueprint.family_approved = True
    with pytest.raises(ValueError, match="match"):
        build_illustration_storyboard(
            build_graph(["Начало"]),
            blueprint,
            quick_identity_bible(blueprint, "Оля"),
        )
