"""Mocked OpenAI adapter tests: no real network or billable calls."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.little_legend.openai_chapter_provider import (
    OpenAIChapterProvider,
    WriterAdapterSettings,
)


def make_client(*, text="Готовая сказочная глава.", finish_reason="stop"):
    response = SimpleNamespace(choices=[
        SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=text),
        ),
    ])
    create = AsyncMock(return_value=response)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )


def approved_brief():
    return {
        "scene_id": "scene_1",
        "hero_brief": {"approved_for_generation": True},
        "parent_original": {"premise": "История от родителей"},
        "literary_direction": {"language": "ru"},
    }


def test_adapter_disabled_by_default():
    with pytest.raises(PermissionError, match="disabled"):
        OpenAIChapterProvider(
            client=make_client(), settings=WriterAdapterSettings(),
        )


@pytest.mark.asyncio
async def test_adapter_sends_approved_brief_and_returns_prose():
    client = make_client()
    adapter = OpenAIChapterProvider(
        client=client, settings=WriterAdapterSettings(enabled=True),
    )
    assert await adapter.write_chapter(approved_brief()) == "Готовая сказочная глава."
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert "История от родителей" in kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_adapter_rejects_unapproved_brief_without_call():
    client = make_client()
    adapter = OpenAIChapterProvider(
        client=client, settings=WriterAdapterSettings(enabled=True),
    )
    brief = approved_brief()
    brief["hero_brief"]["approved_for_generation"] = False
    with pytest.raises(PermissionError, match="Hero approval"):
        await adapter.write_chapter(brief)
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_adapter_rejects_truncated_output():
    client = make_client(finish_reason="length")
    adapter = OpenAIChapterProvider(
        client=client, settings=WriterAdapterSettings(enabled=True),
    )
    with pytest.raises(ValueError, match="incomplete"):
        await adapter.write_chapter(approved_brief())
