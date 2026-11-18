"""Privacy-first character identity bible and scene-to-scene continuity audit.

This module never accepts image bytes, URLs, face embeddings or biometric
templates. It prepares editorial review before a future consented photo pipeline.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.story_graph import StoryGraph


class VisualIdentity(BaseModel):
    mode: Literal["quick", "director"] = "quick"
    hair: str = Field(default="", max_length=200)
    eyes: str = Field(default="", max_length=200)
    face: str = Field(default="", max_length=300)
    distinctive_features: list[str] = Field(default_factory=list, max_length=12)
    proportions: str = Field(default="", max_length=300)
    clothing_signature: str = Field(default="", max_length=300)
    fixed_details: list[str] = Field(default_factory=list, max_length=12)
    forbidden_changes: list[str] = Field(default_factory=list, max_length=12)
    portrait_review: Literal["not_started", "needs_review", "approved", "rejected"] = "not_started"
    parental_photo_consent: bool = False
    parent_reviewed_description: bool = False

    @model_validator(mode="after")
    def validate_approval(self) -> VisualIdentity:
        if self.portrait_review == "approved" and not self.parental_photo_consent:
            raise ValueError("Parental photo consent is required before portrait approval")
        return self


class IdentityBible(BaseModel):
    hero_name: str = Field(min_length=1, max_length=100)
    identity: VisualIdentity = Field(default_factory=VisualIdentity)
    visual_style: str = Field(default="storybook", max_length=100)
    consistency_rules: list[str] = Field(default_factory=list, max_length=20)


def quick_identity_bible(blueprint: BookBlueprint, hero: str) -> IdentityBible:
    character = next((c for c in blueprint.characters if c.role == "hero"), None)
    rules = [
        "Не менять возраст и основные черты лица между сценами",
        "Не обрезать лицо, глаза и характерные приметы",
        "Менять костюм и освещение без изменения узнаваемых черт",
    ]
    if character and character.appearance.strip():
        rules.append("Описание внешности: " + character.appearance.strip())
    if character and character.visual_identity_notes.strip():
        rules.append("Неизменные приметы: " + character.visual_identity_notes.strip())
    return IdentityBible(
        hero_name=hero,
        visual_style=blueprint.controls.illustration_style,
        consistency_rules=rules,
    )


def identity_review(bible: IdentityBible, graph: StoryGraph) -> dict:
    """Report missing visual anchors; never claim automated face similarity."""
    identity = bible.identity
    warnings: list[str] = []
    if not (identity.hair or identity.eyes or identity.face):
        warnings.append("Укажите хотя бы одну опорную черту внешности")
    if not identity.parent_reviewed_description:
        warnings.append("Родитель ещё не подтвердил описание внешности")
    if not identity.parental_photo_consent:
        warnings.append("Нет согласия на обработку фотографии ребёнка")
    if identity.portrait_review != "approved":
        warnings.append("Контрольный портрет ещё не утверждён")
    scenes = [
        {
            "scene_id": node.id,
            "order": node.order,
            "scene": node.summary,
            "visual_rules": bible.consistency_rules + identity.fixed_details,
            "portrait_reference_required": True,
        }
        for node in sorted(graph.nodes, key=lambda n: n.order)
    ]
    return {
        "warnings": warnings,
        "scenes": scenes,
        "ready_for_photo_generation": False,
        "face_similarity_measured": False,
        "human_review_required": True,
        "reference_storage_enabled": False,
    }
