"""Commit a writer chapter and complete its queue job in one transaction.

The queue lease is the authorization to write; stale workers cannot commit.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.editorial_review import EditorialDecision
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.text_ai_disclosure import (
    configured_text_ai_disclosure,
    consent_allows_provider,
)
from app.little_legend.writer_checkpoints import (
    WriterCheckpoint,
    apply_writer_checkpoint,
)
from app.little_legend.writer_queue import JobPolicy, JobStatus, WriterJob, finish_job
from app.little_legend.writer_queue_store import writer_jobs


def verify_commit_authorization(draft: object) -> None:
    """Recheck consent under the story row lock before persisting AI output."""
    if not consent_allows_provider(
        draft.text_ai_consent, configured_text_ai_disclosure()
    ):
        raise PermissionError("AI consent was withdrawn or disclosure changed")
    if not draft.outline_approved:
        raise PermissionError("Parent outline approval was withdrawn")
    if draft.parent_sketch is None or draft.graph is None:
        raise PermissionError("Approved source outline is missing")
    if draft.blueprint is None or not draft.blueprint.family_approved:
        raise PermissionError("Family blueprint approval is missing")


def verify_checkpoint_lease(
    job: WriterJob, checkpoint: WriterCheckpoint, *,
    token: str, now: datetime,
) -> None:
    if job.status != JobStatus.RUNNING or job.lease_token != token:
        raise PermissionError("Writer no longer owns the queue lease")
    if job.lease_expires_at is None or job.lease_expires_at <= now:
        raise PermissionError("Writer lease expired")
    if (
        job.job_id != checkpoint.job_id
        or job.scene_id != checkpoint.scene_id
        or job.expected_revision != checkpoint.expected_revision
    ):
        raise ValueError("Checkpoint does not match queued job")


async def commit_writer_result(
    *, story_id: int, owner_id: int, token: str,
    checkpoint: WriterCheckpoint, policy: JobPolicy,
) -> dict:
    """Atomically update manuscript, receipt, review status and queue status."""
    from app.little_legend.router import StoryDraft, stories

    now = datetime.now(UTC)
    async with async_session_maker() as session:
        # Fixed lock order: queue job first, story second.
        raw_job = (await session.execute(
            select(writer_jobs.c.payload).where(
                writer_jobs.c.job_id == checkpoint.job_id,
                writer_jobs.c.story_id == story_id,
                writer_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw_job is None:
            raise HTTPException(404, "Writer job not found")
        job = WriterJob.model_validate_json(raw_job)
        try:
            verify_checkpoint_lease(job, checkpoint, token=token, now=now)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc

        raw_story = (await session.execute(
            select(stories.c.data).where(
                stories.c.id == story_id,
                stories.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw_story is None:
            raise HTTPException(404, "Story not found")
        draft = StoryDraft.model_validate_json(raw_story)
        try:
            verify_commit_authorization(draft)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        manuscript = draft.manuscript or StoryManuscript(hero_name=draft.hero)
        if manuscript.hero_name != draft.hero:
            raise HTTPException(409, "Manuscript hero mismatch")
        graph = draft.graph or build_graph(draft.scenes)
        try:
            receipt = apply_writer_checkpoint(
                manuscript, checkpoint,
                scene_ids={node.id for node in graph.nodes},
                recorded_jobs=draft.writer_job_ids,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if not receipt.applied:
            raise HTTPException(409, "Checkpoint was already committed")
        completed = finish_job(
            job, token=token, success=True, policy=policy, now=now,
        )
        draft.manuscript = receipt.manuscript
        draft.writer_job_ids[checkpoint.scene_id] = checkpoint.job_id
        draft.editorial_decision = EditorialDecision()
        await session.execute(
            update(stories).where(
                stories.c.id == story_id, stories.c.owner_id == owner_id,
            ).values(data=draft.model_dump_json(), updated_at=now)
        )
        await session.execute(
            update(writer_jobs).where(
                writer_jobs.c.job_id == checkpoint.job_id,
                writer_jobs.c.owner_id == owner_id,
            ).values(
                payload=completed.model_dump_json(),
                status=completed.status.value,
                updated_at=now,
            )
        )
        await session.commit()
        return {
            "job_id": checkpoint.job_id,
            "scene_id": checkpoint.scene_id,
            "revision": receipt.revision,
            "status": completed.status.value,
        }
