"""Internal-only writer checkpoint persistence.

Call from a trusted worker after verifying the job belongs to the owner.
No public HTTP route is registered by this module.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.editorial_review import EditorialDecision
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_checkpoints import (
    CheckpointReceipt,
    WriterCheckpoint,
    apply_writer_checkpoint,
)


async def persist_writer_checkpoint(
    *, story_id: int, owner_id: int, checkpoint: WriterCheckpoint,
) -> CheckpointReceipt:
    """Commit manuscript, job receipt and review invalidation atomically."""
    from app.little_legend.router import StoryDraft, stories

    async with async_session_maker() as session:
        raw = (await session.execute(
            select(stories.c.data).where(
                stories.c.id == story_id, stories.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw is None:
            raise HTTPException(404, "Story not found")
        draft = StoryDraft.model_validate_json(raw)
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
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if receipt.applied:
            draft.manuscript = receipt.manuscript
            draft.writer_job_ids[checkpoint.scene_id] = checkpoint.job_id
            draft.editorial_decision = EditorialDecision()
            await session.execute(
                update(stories).where(
                    stories.c.id == story_id, stories.c.owner_id == owner_id,
                ).values(
                    data=draft.model_dump_json(),
                    updated_at=datetime.now(UTC),
                )
            )
        await session.commit()
        return receipt
