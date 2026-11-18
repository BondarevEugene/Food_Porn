"""Owner-scoped manuscript editing and atomic persistence in existing story JSON.

No migrations, external provider calls or photo handling.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


class ChapterEdit(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    notes: str = Field(default="", max_length=1200)


class ChapterApproval(BaseModel):
    approved: bool


def _ordered(manuscript: StoryManuscript) -> StoryManuscript:
    return manuscript.model_copy(deep=True)


def edit_chapter(
    manuscript: StoryManuscript, scene_id: str, edit: ChapterEdit,
) -> StoryManuscript:
    result = _ordered(manuscript)
    chapter = next((item for item in result.chapters if item.scene_id == scene_id), None)
    if chapter is None:
        raise ValueError("Chapter not found")
    if chapter.approved:
        raise PermissionError("Unlock the chapter before editing")
    chapter.text = edit.text
    chapter.notes = edit.notes
    chapter.revision += 1
    result.parent_approved = False
    return result


def approve_chapter(
    manuscript: StoryManuscript, scene_id: str, approved: bool,
) -> StoryManuscript:
    result = _ordered(manuscript)
    chapter = next((item for item in result.chapters if item.scene_id == scene_id), None)
    if chapter is None:
        raise ValueError("Chapter not found")
    chapter.approved = approved
    result.parent_approved = False
    return result


def upsert_generated_chapter(
    manuscript: StoryManuscript, chapter: ChapterDraft,
) -> StoryManuscript:
    result = _ordered(manuscript)
    current = next(
        (item for item in result.chapters if item.scene_id == chapter.scene_id),
        None,
    )
    if current is not None and current.approved:
        raise PermissionError("Approved chapter cannot be overwritten")
    if current is not None and chapter.revision <= current.revision:
        raise ValueError("Stale chapter revision")
    if current is not None:
        result.chapters.remove(current)
    result.chapters.append(chapter.model_copy(deep=True))
    result.parent_approved = False
    return result


async def mutate_owned_manuscript(
    *, story_id: int, owner_id: int,
    transform,
) -> StoryManuscript:
    """Lock story row, validate manuscript, persist a single atomic mutation."""
    # Import here to avoid circular imports in the API router.
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
            raise HTTPException(409, "Manuscript hero differs from story hero")
        try:
            updated = transform(manuscript, draft)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if updated.hero_name != draft.hero:
            raise HTTPException(409, "Manuscript hero cannot change")
        if updated != manuscript:
            from app.little_legend.editorial_review import EditorialDecision

            draft.editorial_decision = EditorialDecision()
        draft.manuscript = updated
        await session.execute(
            update(stories).where(
                stories.c.id == story_id, stories.c.owner_id == owner_id,
            ).values(data=draft.model_dump_json(), updated_at=datetime.now(UTC))
        )
        await session.commit()
        return updated
