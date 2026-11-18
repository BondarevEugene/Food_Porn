"""Bounded, source-grounded continuity memory for chapter writing.

Only approved outline facts and existing manuscript excerpts are included.
This is a structured context aid, not a semantic truth verifier.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


class MemoryEvent(BaseModel):
    scene_id: str
    order: int = Field(ge=1)
    established_summary: str
    causal_consequence: str = ""


class StoryMemory(BaseModel):
    current_scene_id: str
    established_events: list[MemoryEvent] = Field(default_factory=list)
    upcoming_obligations: list[MemoryEvent] = Field(default_factory=list)
    prior_prose_excerpts: list[dict[str, str]] = Field(default_factory=list)
    provenance: str = "approved_outline_and_saved_manuscript"
    semantic_fidelity_verified: bool = False


def build_story_memory(
    graph: StoryGraph, *, scene_id: str,
    manuscript: StoryManuscript | None = None,
    excerpt_chars: int = 1200, max_prior_chapters: int = 4,
) -> StoryMemory:
    """Build ordered, bounded memory without guessing unstated child facts."""
    if not 100 <= excerpt_chars <= 2500:
        raise ValueError("Invalid excerpt budget")
    if not 1 <= max_prior_chapters <= 12:
        raise ValueError("Invalid chapter budget")
    ordered = sorted(graph.nodes, key=lambda node: node.order)
    current = next((node for node in ordered if node.id == scene_id), None)
    if current is None:
        raise ValueError("Unknown scene")
    prior = [node for node in ordered if node.order < current.order]
    future = [node for node in ordered if node.order > current.order]
    saved = {chapter.scene_id: chapter for chapter in manuscript.chapters} if manuscript else {}
    if set(saved) - {node.id for node in ordered}:
        raise ValueError("Manuscript contains unknown scenes")
    excerpts = [
        {"scene_id": node.id, "text": saved[node.id].text[:excerpt_chars]}
        for node in prior[-max_prior_chapters:] if node.id in saved
    ]
    return StoryMemory(
        current_scene_id=scene_id,
        established_events=[
            MemoryEvent(
                scene_id=node.id, order=node.order,
                established_summary=node.summary,
                causal_consequence=node.consequence,
            ) for node in prior
        ],
        upcoming_obligations=[
            MemoryEvent(
                scene_id=node.id, order=node.order,
                established_summary=node.summary,
                causal_consequence=node.consequence,
            ) for node in future
        ],
        prior_prose_excerpts=excerpts,
    )
