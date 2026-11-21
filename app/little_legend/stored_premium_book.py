"""Assemble a premium book from distinct approved private R2 illustration jobs.

No network calls other than reads through the injected private art store.
The production queue currently supports one job per scene; callers must
explicitly supply one unique completed job for the cover and every moment.
"""
from __future__ import annotations

from app.little_legend.generated_art_store import (
    GeneratedArtStore,
    illustration_key,
    validate_generated_art,
)
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_pdf import render_premium_book
from app.little_legend.premium_visual_contract import BookVisualPlan
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


def assemble_stored_premium_book(
    *,
    store: GeneratedArtStore,
    owner_id: int,
    story_id: int,
    title: str,
    dedication: str,
    graph: StoryGraph,
    manuscript: StoryManuscript,
    plan: BookVisualPlan,
    cover_job: IllustrationJob,
    moment_jobs: dict[str, IllustrationJob],
    approved_moment_ids: set[str],
    cover_approved: bool,
) -> bytes:
    """Fail before any R2 reads if a job, revision or approval is missing."""
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Valid owner and story are required")
    expected = {slot.moment_id for slot in plan.illustrations}
    if not cover_approved or approved_moment_ids != expected:
        raise PermissionError("Complete cover and scene approvals are required")
    if set(moment_jobs) != expected:
        raise PermissionError("Every premium illustration must have a distinct job")
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if not nodes or len(nodes) * 2 != len(plan.illustrations):
        raise ValueError("Visual plan and graph chapter count differ")
    if len(chapters) != len(manuscript.chapters) or (
        set(chapters) != {node.id for node in nodes}
    ):
        raise PermissionError("Complete unique chapters are required")
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in chapters.values()
    ):
        raise PermissionError("Approved manuscript is required")

    jobs = [cover_job, *moment_jobs.values()]
    if len({job.job_id for job in jobs}) != len(jobs):
        raise PermissionError("A generated illustration job cannot be reused")
    # Current scene_id storage is limited to 100 characters and is validated
    # against the chapter graph by the legacy queue. This assembly contract
    # requires independent moment jobs from a future queue upgrade.
    for index, node in enumerate(nodes):
        for slot in plan.illustrations[index * 2:index * 2 + 2]:
            if slot.chapter_index != node.order:
                raise ValueError("Illustration order does not match chapter order")
            job = moment_jobs[slot.moment_id]
            if job.scene_id != slot.moment_id:
                raise PermissionError("Illustration job belongs to another moment")
            if job.expected_revision != chapters[node.id].revision:
                raise PermissionError("Illustration revision is stale")
    if cover_job.scene_id != "premium-cover":
        raise PermissionError("Cover job must be independently identified")
    for job in jobs:
        if (job.owner_id != owner_id or job.story_id != story_id
                or job.status != JobStatus.COMPLETED):
            raise PermissionError("Job ownership or completion state is invalid")

    def read_art(job: IllustrationJob) -> bytes:
        key = illustration_key(
            owner_id=owner_id, story_id=story_id, job_id=job.job_id,
        )
        raw = store.get(key=key)
        validate_generated_art(raw)
        return raw

    # Validate all metadata before fetching private art.
    cover = read_art(cover_job)
    images = {slot.moment_id: read_art(moment_jobs[slot.moment_id])
              for slot in plan.illustrations}
    return render_premium_book(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, plan=plan, cover=cover,
        illustrations=images, approved_moment_ids=approved_moment_ids,
        cover_approved=cover_approved,
    )


def assemble_reviewed_premium_book(
    *,
    store: GeneratedArtStore,
    owner_id: int,
    story_id: int,
    title: str,
    dedication: str,
    graph: StoryGraph,
    manuscript: StoryManuscript,
    plan: BookVisualPlan,
    cover_job: IllustrationJob,
    moment_jobs: dict[str, IllustrationJob],
    approved_moment_ids: set[str],
    cover_approved: bool,
) -> bytes:
    """Production entry point: verify durable batch integrity before R2 reads."""
    from app.little_legend.premium_production_control import audit_premium_batch

    status = audit_premium_batch(
        jobs=[cover_job, *moment_jobs.values()],
        approved_moment_ids=approved_moment_ids,
        cover_approved=cover_approved,
    )
    if not status.ready_for_pdf:
        raise PermissionError(
            "Premium batch not approved: " + ", ".join(status.blocked_reasons)
        )
    if status.owner_id != owner_id or status.story_id != story_id:
        raise PermissionError("Premium batch owner or story differs")
    return assemble_stored_premium_book(
        store=store, owner_id=owner_id, story_id=story_id,
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, plan=plan, cover_job=cover_job,
        moment_jobs=moment_jobs, approved_moment_ids=approved_moment_ids,
        cover_approved=cover_approved,
    )
