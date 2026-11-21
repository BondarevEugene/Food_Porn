"""Premium book production control: deterministic batch audit and readiness.

No paid provider calls, no asset exposure, and no automatic approval of AI art.
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_job_context import restore_premium_job_context
from app.little_legend.writer_queue import JobStatus


class PremiumBatchStatus(BaseModel):
    owner_id: int
    story_id: int
    manifest_fingerprint: str
    expected_images: int = Field(gt=0)
    completed: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    retry_wait: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    dispatched_unresolved: int = Field(ge=0)
    awaiting_review: int = Field(ge=0)
    approved: int = Field(ge=0)
    ready_for_pdf: bool
    blocked_reasons: tuple[str, ...]


def audit_premium_batch(
    *, jobs: list[IllustrationJob],
    approved_moment_ids: set[str] | None = None,
    cover_approved: bool = False,
) -> PremiumBatchStatus:
    """Audit an entire 25-image batch; fail closed on mixed or forged jobs.

    Explicit reviewer decisions are required. Completion alone never implies
    approval of likeness, face-safe crop or chapter-specific composition.
    """
    if not jobs:
        raise ValueError("Premium batch has no jobs")
    contexts = [restore_premium_job_context(job) for job in jobs]
    anchor = contexts[0].manifest
    expected = {request.moment_id for request in anchor.requests}
    seen: set[str] = set()
    job_ids: set[str] = set()
    for job, context in zip(jobs, contexts, strict=True):
        if (context.manifest != anchor or context.plan != contexts[0].plan
                or job.premium_story_fingerprint
                != jobs[0].premium_story_fingerprint):
            raise PermissionError("Premium batch contains inconsistent snapshots")
        if job.scene_id not in expected or job.scene_id in seen:
            raise PermissionError("Premium batch contains unexpected or duplicate slots")
        if job.job_id in job_ids:
            raise PermissionError("Premium batch reuses an illustration job")
        seen.add(job.scene_id)
        job_ids.add(job.job_id)
    if approved_moment_ids is None:
        approved_moment_ids = set()
    required_moments = expected - {"premium-cover"}
    if not approved_moment_ids <= required_moments:
        raise PermissionError("Unknown illustration approval identifiers")
    counts = Counter(job.status for job in jobs)
    completed_ids = {
        job.scene_id for job in jobs if job.status == JobStatus.COMPLETED
    }
    if not approved_moment_ids <= completed_ids:
        raise PermissionError("Cannot approve an unfinished illustration")
    if cover_approved and "premium-cover" not in completed_ids:
        raise PermissionError("Cannot approve an unfinished cover")
    unresolved = sum(
        job.provider_dispatched_at is not None
        and job.status != JobStatus.COMPLETED
        for job in jobs
    )
    missing = expected - seen
    reasons = []
    if missing:
        reasons.append("missing_illustrations")
    if counts[JobStatus.FAILED] or counts[JobStatus.CANCELLED]:
        reasons.append("failed_or_cancelled_jobs")
    if unresolved:
        reasons.append("provider_reconciliation_required")
    if completed_ids != expected:
        reasons.append("generation_incomplete")
    if not cover_approved:
        reasons.append("cover_review_required")
    if approved_moment_ids != required_moments:
        reasons.append("moment_review_required")
    return PremiumBatchStatus(
        owner_id=anchor.owner_id,
        story_id=anchor.story_id,
        manifest_fingerprint=anchor.fingerprint,
        expected_images=len(expected),
        completed=counts[JobStatus.COMPLETED],
        queued=counts[JobStatus.QUEUED],
        running=counts[JobStatus.RUNNING],
        retry_wait=counts[JobStatus.RETRY_WAIT],
        failed=counts[JobStatus.FAILED],
        cancelled=counts[JobStatus.CANCELLED],
        dispatched_unresolved=unresolved,
        awaiting_review=len(required_moments - approved_moment_ids)
        + int(not cover_approved),
        approved=len(approved_moment_ids) + int(cover_approved),
        ready_for_pdf=not reasons,
        blocked_reasons=tuple(reasons),
    )
