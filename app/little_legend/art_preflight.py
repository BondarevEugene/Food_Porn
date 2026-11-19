"""Book-wide illustration preflight shared by API, queue and worker.

A bad chapter must be found before *any* paid image dispatch. The report is
text-only, deterministic and contains no images, secrets or provider calls.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.illustration_runner import (
    directed_scene_for_provider,
)
from app.little_legend.router import StoryDraft


class SceneReadiness(BaseModel):
    scene_id: str
    order: int
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    prompt_chars: int = 0


class BookArtPreflight(BaseModel):
    ready: bool
    scenes_total: int
    scenes_ready: int
    blockers: list[str] = Field(default_factory=list)
    scenes: list[SceneReadiness] = Field(default_factory=list)
    requires_parent_review: bool = True
    photo_likeness_supported: bool = False


def inspect_book_art(draft: StoryDraft) -> BookArtPreflight:
    """Inspect every scene and approval before queueing a whole book."""
    blockers: list[str] = []
    results: list[SceneReadiness] = []
    if draft.graph is None:
        blockers.append("Story graph is missing")
    if draft.manuscript is None:
        blockers.append("Story manuscript is missing")
    elif not draft.manuscript.parent_approved:
        blockers.append("Parent has not approved the manuscript")
    if draft.manuscript is not None and draft.manuscript.hero_name != draft.hero:
        blockers.append("Manuscript hero does not match the story hero")
    if not draft.hero.strip() or len(draft.hero) > 100:
        blockers.append("Invalid hero name")
    style = draft.blueprint.controls.illustration_style if draft.blueprint else "storybook"
    if not style.strip() or len(style) > 120:
        blockers.append("Invalid illustration style")
    from app.little_legend.reviewed_identity_prompt import reviewed_identity_continuity

    try:
        reviewed_identity_continuity(
            blueprint=draft.blueprint, bible=draft.identity_bible,
            hero_name=draft.hero,
        )
    except (ValueError, PermissionError) as exc:
        blockers.append(str(exc))
    if draft.graph is not None:
        chapters = (
            {chapter.scene_id: chapter for chapter in draft.manuscript.chapters}
            if draft.manuscript is not None else {}
        )
        expected = {scene.id for scene in draft.graph.nodes}
        if draft.manuscript is not None and set(chapters) != expected:
            blockers.append("Manuscript chapters do not match the story graph")
        for scene in sorted(draft.graph.nodes, key=lambda item: item.order):
            problems: list[str] = []
            chapter = chapters.get(scene.id)
            if chapter is None:
                problems.append("Chapter is missing")
            elif not chapter.approved:
                problems.append("Chapter is not approved")
            try:
                directed = directed_scene_for_provider(scene)
                if not directed.summary.strip():
                    problems.append("Scene description is empty")
                length = len(directed.summary)
            except ValueError as exc:
                problems.append(str(exc))
                length = 0
            results.append(SceneReadiness(
                scene_id=scene.id, order=scene.order, ready=not problems,
                blockers=problems, prompt_chars=length,
            ))
    return BookArtPreflight(
        ready=not blockers and bool(results) and all(scene.ready for scene in results),
        scenes_total=len(results),
        scenes_ready=sum(scene.ready for scene in results),
        blockers=blockers, scenes=results,
    )


def require_book_art_ready(draft: StoryDraft) -> BookArtPreflight:
    report = inspect_book_art(draft)
    if not report.ready:
        first = report.blockers[:1]
        first.extend(
            f"{scene.scene_id}: {scene.blockers[0]}"
            for scene in report.scenes if scene.blockers
        )
        raise PermissionError("Illustration preflight failed: " + "; ".join(first[:5]))
    return report
