"""Deterministic editorial direction for the Little Legend chapter writer.

These are writing instructions, not a claim that AI prose has passed review.
No external service is invoked and no child biography is inferred.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.blueprint import CreativeControls
from app.little_legend.narrative_design import StoryDesign


class LiteraryDirection(BaseModel):
    language: str
    audience_age: int | None
    reading_level: str
    narrative_person: str
    tone: str
    mode: str
    style_instructions: list[str] = Field(default_factory=list)
    scene_requirements: list[str] = Field(default_factory=list)
    quality_checks: list[str] = Field(default_factory=list)
    human_editor_required: bool = True


def build_literary_direction(
    controls: CreativeControls, design: StoryDesign, *, mode: str,
    scene_goal: str, scene_conflict: str,
) -> LiteraryDirection:
    """Translate approved creative controls into explicit chapter constraints."""
    if mode not in {"quick", "director"}:
        raise ValueError("Unknown literary direction mode")
    if controls.age is None:
        age_style = (
            "Reading age is unknown. Avoid assuming developmental maturity; "
            "request an age choice before claiming age suitability."
        )
    elif controls.age <= 5:
        age_style = (
            "Use short concrete sentences, gentle suspense, audible rhythm, "
            "clear emotional cues, and a reassuring resolution."
        )
    elif controls.age <= 8:
        age_style = (
            "Use vivid actions, clear cause and effect, accessible dialogue, "
            "and solvable clues with an emotionally safe outcome."
        )
    elif controls.age <= 12:
        age_style = (
            "Give supporting characters distinct motives, build fair clues, "
            "and let choices carry understandable consequences."
        )
    else:
        age_style = (
            "Allow nuanced motives, layered conflicts and subtext, while "
            "preserving emotional safety and the approved family boundaries."
        )
    requirements = [
        "Advance the approved scene goal through observable action, not exposition.",
        "Give the child protagonist a consequential choice or contribution.",
        "Use specific sensory details that support the action; avoid ornamental padding.",
        "Make dialogue reveal character or change the situation.",
        "Keep causal links to earlier chapters and avoid contradicting established facts.",
        "Do not invent personal facts about the real child.",
        "Respect all excluded topics and emotional-safety constraints.",
    ]
    if scene_goal.strip():
        requirements.append(f"Approved scene goal: {scene_goal.strip()}")
    if scene_conflict.strip():
        requirements.append(f"Approved scene conflict: {scene_conflict.strip()}")
    checks = [
        "Every important event has a cause and a consequence.",
        "The protagonist remains active rather than being rescued by coincidence.",
        "Character names, relationships and established world rules remain consistent.",
        "No unexplained reversal, repeated scene or artificial cliffhanger.",
        "The ending of this chapter changes the story state.",
        "Human editorial and parent approval are still required.",
    ]
    if design.theme.strip():
        requirements.append("Express the approved theme through character actions.")
    if mode == "director":
        requirements.extend([
            "Use the approved theme as subtext, not an explicit moral lecture.",
            "Vary sentence cadence and scene pacing without losing clarity.",
            "Ensure emotional changes arise from concrete events.",
        ])
    return LiteraryDirection(
        language=controls.language,
        audience_age=controls.age,
        reading_level=controls.reading_level,
        narrative_person=controls.narrative_person,
        tone=controls.tone,
        mode=mode,
        style_instructions=[
            f"Write in language code {controls.language}.",
            age_style,
            f"Use {controls.narrative_person}-person narration.",
            f"Maintain a {controls.tone} emotional tone.",
            f"Target {controls.reading_level} reading level.",
        ],
        scene_requirements=requirements,
        quality_checks=checks,
    )
