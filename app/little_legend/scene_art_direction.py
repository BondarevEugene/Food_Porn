"""Deterministic, scene-specific art direction; no remote image generation.

The immutable character description is repeated in every scene brief. Scene
content comes from the approved graph; unspecified appearance stays unspecified.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.little_legend.hero_contract import FactPriority, HeroContract
from app.little_legend.story_graph import StoryGraph


class SceneArtBrief(BaseModel):
    scene_id: str
    scene_order: int = Field(ge=1, le=40)
    scene_title: str
    hero_name: str
    identity_anchor: tuple[str, ...] = Field(min_length=1)
    scene_action: str
    setting_and_context: str
    continuity_rules: tuple[str, ...]
    forbidden_inventions: tuple[str, ...]
    review_required: bool = True
    generated: bool = False

    @model_validator(mode="after")
    def no_implicit_generation(self) -> SceneArtBrief:
        if self.generated or not self.review_required:
            raise ValueError("Scene briefs are not approved generated illustrations")
        return self


class BookArtDirection(BaseModel):
    hero_name: str
    briefs: list[SceneArtBrief] = Field(min_length=1, max_length=40)
    identity_consistency_verified: bool = False
    images_generated: bool = False
    human_review_required: bool = True


def build_scene_art_direction(
    contract: HeroContract, graph: StoryGraph,
) -> BookArtDirection:
    """Prepare all distinct scenes without altering immutable character facts."""
    if not contract.family_approved:
        raise PermissionError("Parent-approved hero identity is required")
    identity = tuple(
        f"{fact.key}: {fact.value}" for fact in contract.facts
        if fact.priority == FactPriority.IMMUTABLE
    )
    if not identity:
        raise ValueError("Immutable hero identity facts are required")
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    briefs = []
    for node in nodes:
        if not node.summary.strip():
            raise ValueError(f"Scene {node.id} lacks a visual narrative summary")
        action = node.illustration_prompt.strip() or node.summary.strip()
        context = " | ".join(
            item for item in (
                node.summary.strip(), node.goal.strip(),
                node.conflict.strip(), node.consequence.strip(),
            ) if item
        )
        briefs.append(SceneArtBrief(
            scene_id=node.id,
            scene_order=node.order,
            scene_title=node.title,
            hero_name=contract.hero_name,
            identity_anchor=identity,
            scene_action=action,
            setting_and_context=context,
            continuity_rules=(
                "Сохранять неизменные признаки героя во всех сценах.",
                "Изменять только действие, позу, окружение и одежду, "
                "если они явно заданы в исходном описании сцены.",
                "Не придумывать детали внешности, которых нет в утверждённых данных.",
                "Композиция должна соответствовать событию именно этой главы.",
            ),
            forbidden_inventions=tuple(contract.forbidden_inventions),
        ))
    return BookArtDirection(hero_name=contract.hero_name, briefs=briefs)


def art_direction_report(direction: BookArtDirection, graph: StoryGraph) -> dict:
    """Audit structural coverage; never claim visual likeness was verified."""
    expected = {node.id for node in graph.nodes}
    actual = [brief.scene_id for brief in direction.briefs]
    return {
        "expected_scenes": len(expected),
        "prepared_scenes": len(actual),
        "missing_scenes": sorted(expected - set(actual)),
        "unexpected_scenes": sorted(set(actual) - expected),
        "duplicate_scenes": sorted({
            scene_id for scene_id in actual if actual.count(scene_id) > 1
        }),
        "identity_consistency_verified": False,
        "images_generated": False,
        "requires_human_visual_review": True,
    }
