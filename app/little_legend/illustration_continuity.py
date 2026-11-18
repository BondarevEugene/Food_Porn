"""Illustration continuity specifications for a parent-reviewed hero.

No image upload, face recognition, embeddings, provider call or similarity
score is implemented. These specifications are text-only and fail closed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.character_identity import IdentityBible
from app.little_legend.consent import ConsentRecord
from app.little_legend.portrait_studio import PortraitPlan
from app.little_legend.story_graph import StoryGraph


class IllustrationReview(BaseModel):
    scene_id: str
    parent_approved: bool = False
    face_recognizable: bool = False
    stable_features: bool = False
    age_consistent: bool = False
    no_unwanted_changes: bool = False
    notes: str = Field(default="", max_length=1200)


def illustration_scene_specs(
    graph: StoryGraph, bible: IdentityBible, plan: PortraitPlan,
) -> list[dict]:
    """Propagate the same appearance constraints into every scene."""
    identity = bible.identity
    anchors = {
        "hero_name": bible.hero_name,
        "hair": identity.hair,
        "eyes": identity.eyes,
        "face": identity.face,
        "distinctive_features": identity.distinctive_features,
        "proportions": identity.proportions,
        "fixed_details": identity.fixed_details,
        "clothing_signature": identity.clothing_signature,
        "forbidden_changes": identity.forbidden_changes,
    }
    return [
        {
            "scene_id": node.id,
            "scene_summary": node.summary,
            "illustration_prompt": node.illustration_prompt,
            "hero_anchors": anchors,
            "style": bible.visual_style,
            "framing": plan.framing,
            "lighting": plan.lighting,
            "preferred_outfit": plan.preferred_outfit,
            "avoid": plan.avoid,
            "requirements": [
                "Сохранять узнаваемые черты одного героя во всех сценах.",
                "Не менять возраст, пропорции лица и постоянные приметы.",
                "Допустимо менять позу, костюм и выражение лица по сюжету.",
                "Не скрывать лицо без художественной необходимости.",
                "Не создавать неподтверждённые биографические детали.",
            ],
            "reference_photo_attached": False,
            "generation_enabled": False,
        }
        for node in sorted(graph.nodes, key=lambda item: item.order)
    ]


def illustration_approval_gate(
    graph: StoryGraph,
    reviews: list[IllustrationReview],
    bible: IdentityBible,
    consent: ConsentRecord,
) -> dict:
    """Require manual review and secure-photo launch before likeness claims."""
    expected = {node.id for node in graph.nodes}
    seen = {review.scene_id for review in reviews}
    approved = {
        review.scene_id for review in reviews
        if all((
            review.parent_approved,
            review.face_recognizable,
            review.stable_features,
            review.age_consistent,
            review.no_unwanted_changes,
        ))
    }
    return {
        "missing_reviews": sorted(expected - seen),
        "rejected_or_unapproved": sorted(expected - approved),
        "unexpected_reviews": sorted(seen - expected),
        "parent_reviewed_description": bible.identity.parent_reviewed_description,
        "photo_consent_active": consent.photo_consent_active,
        "exact_likeness_guaranteed": False,
        "photo_generation_enabled": False,
        "ready_for_photo_based_publication": False,
    }
