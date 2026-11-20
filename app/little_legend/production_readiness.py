"""Deterministic production readiness report for Little Legend books.

No AI calls, network traffic, database access or customer media in this layer.
The report is advisory; actual export and delivery must enforce their own gates.
"""
from __future__ import annotations

from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


class ProductionStage(StrEnum):
    MANUSCRIPT = "manuscript"
    ILLUSTRATIONS = "illustrations"
    EDITORIAL = "editorial"
    EXPORT = "export"
    DELIVERY = "delivery"


class ReadinessIssue(BaseModel):
    code: str
    stage: ProductionStage
    scene_id: str | None = None


class ProductionReadiness(BaseModel):
    ready_for_export: bool
    ready_for_delivery: bool
    completed_scenes: int = Field(ge=0)
    total_scenes: int = Field(ge=0)
    issues: list[ReadinessIssue] = Field(default_factory=list)


def assess_production(
    *, graph: StoryGraph, manuscript: StoryManuscript,
    jobs: list[IllustrationJob], editorial_approved: bool = False,
    pdf_verified: bool = False,
) -> ProductionReadiness:
    """Expose stable machine-readable blockers without leaking story text."""
    issues: list[ReadinessIssue] = []

    def add(code: str, stage: ProductionStage, scene_id: str | None = None) -> None:
        issues.append(ReadinessIssue(code=code, stage=stage, scene_id=scene_id))

    scene_ids = [node.id for node in graph.nodes]
    expected = set(scene_ids)
    if not scene_ids:
        add("scenes_missing", ProductionStage.MANUSCRIPT)
    if len(expected) != len(scene_ids):
        add("duplicate_scene_ids", ProductionStage.MANUSCRIPT)
    if len({chapter.scene_id for chapter in manuscript.chapters}) != len(manuscript.chapters):
        add("duplicate_chapters", ProductionStage.MANUSCRIPT)
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    counts = Counter(job.scene_id for job in jobs)
    if not manuscript.parent_approved:
        add("parent_approval_missing", ProductionStage.MANUSCRIPT)
    if not manuscript.hero_name.strip():
        add("hero_missing", ProductionStage.MANUSCRIPT)
    for scene_id in scene_ids:
        chapter = chapters.get(scene_id)
        if chapter is None:
            add("chapter_missing", ProductionStage.MANUSCRIPT, scene_id)
        elif not chapter.approved:
            add("chapter_unapproved", ProductionStage.MANUSCRIPT, scene_id)
        matching = [job for job in jobs if job.scene_id == scene_id]
        if counts[scene_id] != 1:
            add("illustration_job_count_invalid", ProductionStage.ILLUSTRATIONS, scene_id)
        elif (matching[0].status != JobStatus.COMPLETED
              or matching[0].provider_dispatched_at is None):
            add("illustration_incomplete", ProductionStage.ILLUSTRATIONS, scene_id)
        elif chapter is not None and matching[0].expected_revision != chapter.revision:
            add("illustration_revision_stale", ProductionStage.ILLUSTRATIONS, scene_id)
    for scene_id in sorted(set(chapters) - expected):
        add("unexpected_chapter", ProductionStage.MANUSCRIPT, scene_id)
    for scene_id in sorted(set(counts) - expected):
        add("unexpected_illustration", ProductionStage.ILLUSTRATIONS, scene_id)
    if not editorial_approved:
        add("editorial_approval_missing", ProductionStage.EDITORIAL)
    ready = not issues
    if not pdf_verified:
        add("pdf_not_verified", ProductionStage.EXPORT)
    return ProductionReadiness(
        ready_for_export=ready,
        ready_for_delivery=ready and pdf_verified,
        completed_scenes=sum(
            1 for scene_id in expected
            if counts[scene_id] == 1
            and scene_id in chapters
            and chapters[scene_id].approved
            and any(
                job.scene_id == scene_id
                and job.status == JobStatus.COMPLETED
                and job.provider_dispatched_at is not None
                and job.expected_revision == chapters[scene_id].revision
                for job in jobs
            )
        ),
        total_scenes=len(expected),
        issues=issues,
    )
