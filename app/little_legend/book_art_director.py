"""Deterministic, book-wide visual directing for original fictional art.

A director's shot plan is derived from approved story beats. It is not a
likeness assessment, an image generator, or permission to process child photos.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from app.little_legend.story_graph import SceneNode, StoryGraph

Shot = Literal["wide", "medium", "close", "dynamic", "establishing"]
Mood = Literal["wonder", "warmth", "mystery", "tension", "triumph", "calm"]

_SHOTS: dict[str, Shot] = {
    "opening": "establishing", "inciting": "wide", "ally": "medium",
    "clue": "close", "puzzle": "close", "danger": "dynamic",
    "reversal": "wide", "relationship": "medium", "revelation": "close",
    "plan": "medium", "climax": "dynamic", "resolution": "wide",
}
_MOODS: dict[str, Mood] = {
    "opening": "wonder", "inciting": "mystery", "ally": "warmth",
    "clue": "mystery", "puzzle": "mystery", "danger": "tension",
    "reversal": "tension", "relationship": "warmth", "revelation": "wonder",
    "plan": "calm", "climax": "triumph", "resolution": "calm",
}
_SHOT_INSTRUCTION: dict[Shot, str] = {
    "wide": "Wide shot: show the hero within the story setting.",
    "medium": "Medium shot: show character interaction and body language.",
    "close": "Close shot: emphasize the story clue or expression, no cropped face.",
    "dynamic": "Dynamic shot: depict the decisive action with clear silhouettes.",
    "establishing": "Establishing shot: introduce the world and its scale.",
}
_MOOD_INSTRUCTION: dict[Mood, str] = {
    "wonder": "Atmosphere: wonder and discovery.",
    "warmth": "Atmosphere: warmth and companionship.",
    "mystery": "Atmosphere: gentle mystery, never horror.",
    "tension": "Atmosphere: age-appropriate suspense, no graphic violence.",
    "triumph": "Atmosphere: earned courage and triumph.",
    "calm": "Atmosphere: quiet resolution and reassurance.",
}
_SAFE_AREA = (
    "Print composition: keep faces, hands and story-critical objects clear "
    "of the trim, bleed and center gutter; leave calm negative space for text."
)


class DirectedShot(BaseModel):
    scene_id: str
    order: int
    beat: str
    shot: Shot
    mood: Mood
    prompt: str
    warnings: list[str] = Field(default_factory=list)


class BookShotPlan(BaseModel):
    shots: list[DirectedShot]
    warnings: list[str] = Field(default_factory=list)
    photo_likeness_verified: bool = False
    images_generated: bool = False


def _scene_text(scene: SceneNode) -> str:
    action = scene.illustration_prompt.strip()
    summary = scene.summary.strip()
    if not summary:
        raise ValueError(f"Scene {scene.id} lacks story context")
    if action:
        return f"Scene action and composition: {action}. Story context: {summary}"
    return summary


def _signature(scene: SceneNode) -> str:
    text = scene.illustration_prompt.strip() or scene.summary.strip()
    return re.sub(r"\s+", " ", text.casefold()).strip(" .,!?:;")


def plan_book_shots(graph: StoryGraph) -> BookShotPlan:
    """Create a repeatable shot list, with warnings for duplicated scene art."""
    scenes = sorted(graph.nodes, key=lambda scene: scene.order)
    signatures = Counter(_signature(scene) for scene in scenes if _signature(scene))
    warnings: list[str] = []
    shots: list[DirectedShot] = []
    previous: Shot | None = None
    for scene in scenes:
        shot = _SHOTS[scene.beat]
        # Avoid three consecutive identical shots while preserving story intent.
        if len(shots) >= 2 and shots[-1].shot == shots[-2].shot == shot:
            shot = "wide" if shot != "wide" else "medium"
        mood = _MOODS[scene.beat]
        scene_warnings: list[str] = []
        if signatures[_signature(scene)] > 1:
            scene_warnings.append("Duplicate visual action across chapters")
        if previous == shot:
            scene_warnings.append("Adjacent scenes share the same camera distance")
        text = _scene_text(scene)
        prompt = " ".join((
            text, _SHOT_INSTRUCTION[shot], _MOOD_INSTRUCTION[mood], _SAFE_AREA,
        ))
        if len(prompt) > 2000:
            raise ValueError(
                f"Directed scene {scene.id} exceeds provider prompt limit"
            )
        shots.append(DirectedShot(
            scene_id=scene.id, order=scene.order, beat=scene.beat,
            shot=shot, mood=mood, prompt=prompt, warnings=scene_warnings,
        ))
        previous = shot
    if len({shot.shot for shot in shots}) == 1 and len(shots) >= 3:
        warnings.append("All illustrations use the same camera distance")
    if any(shot.warnings for shot in shots):
        warnings.append("Some scenes need visual variety review")
    return BookShotPlan(shots=shots, warnings=warnings)


def directed_scene_from_plan(scene: SceneNode, shot: DirectedShot) -> SceneNode:
    if scene.id != shot.scene_id or scene.order != shot.order:
        raise ValueError("Directed shot does not match source scene")
    return scene.model_copy(update={"summary": shot.prompt})
