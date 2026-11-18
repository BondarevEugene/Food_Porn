"""Manuscript download is owner-scoped and never substitutes outlines."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.little_legend.router import StoryDraft, download_manuscript_pdf
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


@pytest.mark.asyncio
async def test_download_full_manuscript_returns_private_pdf():
    draft = StoryDraft(
        title="Приключение Марты", hero="Марта",
        graph=build_graph(["Первый эпизод"]),
        manuscript=StoryManuscript(
            hero_name="Марта",
            chapters=[ChapterDraft(scene_id="scene_1", text="Марта нашла ключ.")],
        ),
    )
    with patch(
        "app.little_legend.router._owned_draft",
        new_callable=AsyncMock, return_value=draft,
    ) as lookup:
        response = await download_manuscript_pdf(17, 42)
    lookup.assert_awaited_once_with(17, 42)
    assert response.body.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_download_without_manuscript_returns_conflict():
    with patch(
        "app.little_legend.router._owned_draft",
        new_callable=AsyncMock, return_value=StoryDraft(),
    ):
        with pytest.raises(HTTPException) as error:
            await download_manuscript_pdf(17, 42)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_download_incomplete_manuscript_returns_conflict():
    draft = StoryDraft(
        hero="Марта", graph=build_graph(["Первый", "Второй"]),
        manuscript=StoryManuscript(
            hero_name="Марта",
            chapters=[ChapterDraft(scene_id="scene_1", text="Текст")],
        ),
    )
    with patch(
        "app.little_legend.router._owned_draft",
        new_callable=AsyncMock, return_value=draft,
    ):
        with pytest.raises(HTTPException) as error:
            await download_manuscript_pdf(17, 42)
    assert error.value.status_code == 409
