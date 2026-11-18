"""Whole-book illustration storyboard; planning only, never image generation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.character_identity import IdentityBible
from app.little_legend.illustration_direction import build_illustration_brief
from app.little_legend.story_graph import StoryGraph


class IllustrationShot(BaseModel):
    scene_id: str
    chapter: int = Field(ge=1)
    title: str
    prompt: str
    framing: Literal["wide", "medium"] = "medium"
    continuity_anchors: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    approval_status: Literal["draft", "approved", "changes_requested"] = "draft"
    image_generated: bool = False


class IllustrationStoryboard(BaseModel):
    hero_name: str
    visual_style: str
    shots: list[IllustrationShot]
    parent_approval_required: bool = True
    photo_likeness_verified: bool = False
    remote_generation_performed: bool = False


def build_illustration_storyboard(
    graph: StoryGraph, blueprint: BookBlueprint, identity: IdentityBible,
) -> IllustrationStoryboard:
    """Generate editable shot briefs from approved character and story inputs."""
    if not blueprint.family_approved:
        raise PermissionError("Family must approve the story blueprint")
    heroes = [item for item in blueprint.characters if item.role == "hero"]
    if len(heroes) != 1 or heroes[0].name != identity.hero_name:
        raise ValueError("Approved hero and visual identity must match")
    hero = heroes[0]
    anchors = [
        value for value in (
            hero.appearance.strip(), hero.visual_identity_notes.strip(),
            identity.identity.hair.strip(), identity.identity.eyes.strip(),
            identity.identity.face.strip(), *identity.identity.fixed_details,
        ) if value
    ]
    shots = []
    for node in sorted(graph.nodes, key=lambda item: item.order):
        brief = build_illustration_brief(node, blueprint, hero=hero.name)
        shots.append(IllustrationShot(
            scene_id=node.id,
            chapter=node.order,
            title=node.title,
            prompt=brief.prompt,
            framing="wide" if node.beat in {"opening", "resolution"} else "medium",
            continuity_anchors=anchors,
            avoid=[*brief.negative_constraints, *identity.identity.forbidden_changes],
        ))
    return IllustrationStoryboard(
        hero_name=hero.name,
        visual_style=identity.visual_style,
        shots=shots,
    )
