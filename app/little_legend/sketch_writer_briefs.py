"""Compose chapter briefs from the parent's original story sketch.

The text stays local until a separately authorized AI worker invokes a provider.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.client_sketch import ParentSketch
from app.little_legend.hero_contract import HeroContract
from app.little_legend.manuscript_studio import chapter_writing_jobs
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


class SketchWritingSettings(BaseModel):
    mode: str = Field(default="quick", pattern="^(quick|director)$")
    chapter_min_words: int = Field(default=200, ge=80, le=2000)
    chapter_max_words: int = Field(default=550, ge=100, le=3000)
    require_parent_outline_approval: bool = True
    avoid_unverified_child_facts: bool = True


def compose_sketch_chapter_briefs(
    *, sketch: ParentSketch, graph: StoryGraph,
    contract: HeroContract, blueprint: BookBlueprint,
    design: StoryDesign, settings: SketchWritingSettings,
    outline_approved: bool, existing: StoryManuscript | None = None,
) -> list[dict]:
    """Prepare complete per-chapter context and immutable source constraints."""
    if not contract.family_approved or not blueprint.family_approved:
        raise PermissionError("Approved child profile is required")
    if settings.require_parent_outline_approval and not outline_approved:
        raise PermissionError("Parent must approve the story outline")
    if settings.chapter_min_words > settings.chapter_max_words:
        raise ValueError("Minimum chapter length exceeds maximum")
    if existing is not None and existing.hero_name != contract.hero_name:
        raise ValueError("Manuscript hero differs from approved profile")

    prior = {
        chapter.scene_id: chapter for chapter in existing.chapters
    } if existing else {}
    jobs = chapter_writing_jobs(graph, contract, blueprint, design)
    all_summaries = [
        {"scene_id": node.id, "order": node.order, "summary": node.summary}
        for node in sorted(graph.nodes, key=lambda item: item.order)
    ]
    briefs = []
    for job in jobs:
        chapter = prior.get(job["scene_id"])
        if chapter is not None and chapter.approved:
            continue
        earlier = [
            {"scene_id": node["scene_id"], "summary": node["summary"],
             "written_text": prior[node["scene_id"]].text[:2500]
             if node["scene_id"] in prior else ""}
            for node in all_summaries if node["order"] < job["chapter"]
        ]
        briefs.append({
            **job,
            "parent_original": {
                "premise": sketch.premise,
                "ordered_moments": sketch.moments,
                "wish": sketch.wish,
                "challenge": sketch.challenge,
                "decisive_choice": sketch.special_choice,
                "ending": sketch.ending,
                "lesson": sketch.lesson,
                "relationships": sketch.relationships,
                "excluded_topics": sketch.avoid,
                "emotional_safety": sketch.emotional_safety,
            },
            "continuity": {
                "complete_outline": all_summaries,
                "previous_chapters": earlier,
            },
            "length": {
                "minimum_words": settings.chapter_min_words,
                "maximum_words": settings.chapter_max_words,
            },
            "editorial_rules": [
                "Write literary prose, not an outline or list.",
                "The child's choices drive the central plot.",
                "Honor the parent's source moments and their chronology.",
                "Do not introduce excluded topics, even as a twist.",
                "Do not present invented biography as fact about the child.",
                "Maintain character, world and event continuity.",
                "Respect the requested language and reading age.",
                "Leave unspecified personal facts unspecified.",
            ],
        })
    return briefs
