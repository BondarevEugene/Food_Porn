"""OpenAI adapter tests with a local fake, no network calls."""
from types import SimpleNamespace

import pytest

from app.little_legend.openai_story_writer import (
    OpenAIChapterWriter,
    WriterSettings,
)


class FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content="Марта открыла дверь."))
        ])


@pytest.mark.asyncio
async def test_writer_sends_only_approved_text_brief():
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    writer = OpenAIChapterWriter(client, WriterSettings(model="test-model"))
    result = await writer.write_chapter({
        "hero_brief": {
            "approved_for_generation": True,
            "hero": {"hero_name": "Марта"},
        },
        "scene_id": "scene_1",
    })
    assert result == "Марта открыла дверь."
    assert completions.calls[0]["model"] == "test-model"
    assert "Марта" in completions.calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_writer_rejects_unapproved_profile_without_network():
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    writer = OpenAIChapterWriter(client, WriterSettings(model="test-model"))
    with pytest.raises(PermissionError):
        await writer.write_chapter({
            "hero_brief": {"approved_for_generation": False}
        })
    assert completions.calls == []
