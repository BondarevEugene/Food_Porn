"""Owner-scoped private book download rejects incomplete work without S3."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.little_legend.router import StoryDraft, download_stored_illustrated_book
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


@pytest.mark.asyncio
async def test_private_book_download_requires_manuscript_before_queue_lookup():
    with patch(
        "app.little_legend.router._owned_draft",
        new_callable=AsyncMock, return_value=StoryDraft(),
    ):
        with pytest.raises(HTTPException) as error:
            await download_stored_illustrated_book(17, 42)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_private_book_download_requires_completed_illustrations():
    draft = StoryDraft(
        hero="Marta", graph=build_graph(["Forest"]),
        manuscript=StoryManuscript(
            hero_name="Marta", parent_approved=True,
            chapters=[ChapterDraft(
                scene_id="scene_1", text="A forest", approved=True,
            )],
        ),
    )
    with (
        patch(
            "app.little_legend.router._owned_draft",
            new_callable=AsyncMock, return_value=draft,
        ),
        patch(
            "app.little_legend.illustration_queue_store.list_owner_illustration_jobs",
            new_callable=AsyncMock, return_value=[],
        ) as jobs,
    ):
        with pytest.raises(HTTPException) as error:
            await download_stored_illustrated_book(17, 42)
    jobs.assert_awaited_once_with(story_id=17, owner_id=42)
    assert error.value.status_code == 409
