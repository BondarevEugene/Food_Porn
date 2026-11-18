"""Text-only illustration consistency gates."""
from app.little_legend.character_identity import IdentityBible, VisualIdentity
from app.little_legend.consent import ConsentRecord
from app.little_legend.illustration_continuity import (
    IllustrationReview,
    illustration_approval_gate,
    illustration_scene_specs,
)
from app.little_legend.portrait_studio import PortraitPlan
from app.little_legend.story_graph import build_graph


def test_same_hero_anchors_in_all_scenes():
    graph = build_graph(["Лес", "Замок"])
    bible = IdentityBible(
        hero_name="Марта",
        identity=VisualIdentity(hair="рыжие кудри", eyes="зелёные"),
    )
    specs = illustration_scene_specs(graph, bible, PortraitPlan())
    assert len(specs) == 2
    assert specs[0]["hero_anchors"] == specs[1]["hero_anchors"]
    assert specs[0]["hero_anchors"]["hair"] == "рыжие кудри"
    assert all(not spec["generation_enabled"] for spec in specs)


def test_parent_review_cannot_enable_unlaunched_photo_pipeline():
    graph = build_graph(["Лес"])
    reviews = [IllustrationReview(
        scene_id="scene_1", parent_approved=True, face_recognizable=True,
        stable_features=True, age_consistent=True, no_unwanted_changes=True,
    )]
    result = illustration_approval_gate(
        graph, reviews, IdentityBible(hero_name="Марта"), ConsentRecord()
    )
    assert result["ready_for_photo_based_publication"] is False
    assert result["exact_likeness_guaranteed"] is False
    assert result["photo_consent_active"] is False
