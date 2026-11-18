"""Provider-independent, approval-gated Little Legend chapter writing engine.

External AI calls are made only by an explicitly supplied provider.
No image data, URLs or biometric identifiers are accepted.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.hero_contract import HeroContract
from app.little_legend.manuscript_studio import chapter_writing_jobs
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import StoryGraph

MAX_CHAPTER_CHARACTERS = 20000


class WriterProvider(Protocol):
    async def write_chapter(self, brief: dict) -> str: ...


class ChapterDraft(BaseModel):
    scene_id: str
    text: str = Field(min_length=1, max_length=MAX_CHAPTER_CHARACTERS)
    approved: bool = False
    revision: int = Field(default=1, ge=1)
    notes: str = Field(default="", max_length=1200)


class StoryManuscript(BaseModel):
    hero_name: str
    chapters: list[ChapterDraft] = Field(default_factory=list, max_length=40)
    parent_approved: bool = False

    @model_validator(mode="after")
    def unique_scene_ids(self) -> StoryManuscript:
        ids = [chapter.scene_id for chapter in self.chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate scene IDs")
        return self


@dataclass(frozen=True)
class WritingPolicy:
    enabled: bool = False
    max_chapters_per_request: int = 12


def _validate_plan(
    graph: StoryGraph, contract: HeroContract, blueprint: BookBlueprint,
) -> None:
    if not contract.family_approved:
        raise PermissionError("Parental hero description approval is required")
    if not blueprint.family_approved:
        raise PermissionError("Family blueprint approval is required")
    if not any(
        character.role == "hero" and character.name == contract.hero_name
        for character in blueprint.characters
    ):
        raise ValueError("Story hero conflicts with approved character profile")


def manuscript_review(manuscript: StoryManuscript, graph: StoryGraph) -> dict:
    """Structural gate, not a semantic proof of child likeness."""
    expected = {node.id for node in graph.nodes}
    actual = {chapter.scene_id for chapter in manuscript.chapters}
    unapproved = [
        chapter.scene_id for chapter in manuscript.chapters if not chapter.approved
    ]
    complete = (
        not (expected - actual) and not (actual - expected)
        and not unapproved and manuscript.parent_approved
    )
    return {
        "missing_scenes": sorted(expected - actual),
        "unexpected_scenes": sorted(actual - expected),
        "unapproved_scenes": unapproved,
        "structurally_approved": complete,
        "semantic_fidelity_verified": False,
        "ready_for_publication": False,
    }


async def write_manuscript(
    provider: WriterProvider,
    graph: StoryGraph,
    contract: HeroContract,
    blueprint: BookBlueprint,
    design: StoryDesign,
    *,
    policy: WritingPolicy,
    existing: StoryManuscript | None = None,
    requested_scenes: set[str] | None = None,
    on_chapter: Callable[[ChapterDraft], Awaitable[None]] | None = None,
) -> StoryManuscript:
    """Generate only unapproved or explicitly selected chapters.

    Explicit regeneration of an approved chapter is forbidden. Results can be
    persisted after each chapter by the caller through on_chapter. No remote
    provider is constructed or configured by this module.
    """
    if not policy.enabled:
        raise PermissionError("AI writing is disabled")
    _validate_plan(graph, contract, blueprint)
    if existing is not None and existing.hero_name != contract.hero_name:
        raise ValueError("Cannot change the manuscript hero")
    jobs = chapter_writing_jobs(graph, contract, blueprint, design)
    ids = {job["scene_id"] for job in jobs}
    if requested_scenes is not None and not requested_scenes <= ids:
        raise ValueError("Unknown requested scene")
    current = {chapter.scene_id: chapter.model_copy(deep=True)
               for chapter in existing.chapters} if existing else {}
    if set(current) - ids:
        raise ValueError("Existing manuscript references unknown scenes")
    targets = [
        job for job in jobs
        if (requested_scenes is None or job["scene_id"] in requested_scenes)
        and job["scene_id"] not in {
            key for key, chapter in current.items() if chapter.approved
        }
        and (requested_scenes is not None or job["scene_id"] not in current)
    ]
    if requested_scenes is not None and any(
        current.get(scene_id) is not None and current[scene_id].approved
        for scene_id in requested_scenes
    ):
        raise PermissionError("Approved chapters must be unlocked before regeneration")
    if len(targets) > policy.max_chapters_per_request:
        raise ValueError("Too many chapters in a single request")
    for job in targets:
        text = await provider.write_chapter(job)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Writer returned an empty chapter")
        previous = current.get(job["scene_id"])
        chapter = ChapterDraft(
            scene_id=job["scene_id"], text=text.strip(),
            revision=previous.revision + 1 if previous else 1,
        )
        current[chapter.scene_id] = chapter
        if on_chapter is not None:
            await on_chapter(chapter)
    return StoryManuscript(
        hero_name=contract.hero_name,
        chapters=[current[job["scene_id"]] for job in jobs
                  if job["scene_id"] in current],
        parent_approved=False if targets else (
            existing.parent_approved if existing else False
        ),
    )
