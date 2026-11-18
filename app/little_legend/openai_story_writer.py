"""Opt-in OpenAI text writer adapter for Little Legend.

No image data is handled. This adapter is not connected to public endpoints;
the caller must enforce ownership, approvals and provider data policy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.little_legend.story_writer import MAX_CHAPTER_CHARACTERS


@dataclass(frozen=True)
class WriterSettings:
    model: str
    max_output_tokens: int = 2400
    temperature: float = 0.7

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Writer model must be configured")
        if not 256 <= self.max_output_tokens <= 8000:
            raise ValueError("Invalid output token budget")
        if not 0 <= self.temperature <= 1:
            raise ValueError("Invalid temperature")


class OpenAIChapterWriter:
    """Adapter around an injected AsyncOpenAI-compatible client.

    The engine's disabled-by-default WritingPolicy must be checked separately.
    """

    def __init__(self, client: Any, settings: WriterSettings) -> None:
        self._client = client
        self._settings = settings

    async def write_chapter(self, brief: dict) -> str:
        if brief.get("hero_brief", {}).get("approved_for_generation") is not True:
            raise PermissionError("Unapproved hero profile cannot be sent to AI")
        response = await self._client.chat.completions.create(
            model=self._settings.model,
            max_tokens=self._settings.max_output_tokens,
            temperature=self._settings.temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты профессиональный детский писатель. Пиши только "
                        "литературный текст одной главы на языке из задания. "
                        "Ребёнок из утверждённого профиля — единственный главный "
                        "герой. Не изменяй факты о нём, не выдумывай биографию, "
                        "диагнозы или травмы. Не заменяй героя помощниками. "
                        "Учитывай возраст, характер, соседние сцены и причинность. "
                        "Никаких комментариев о процессе генерации."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(brief, ensure_ascii=False),
                },
            ],
        )
        choices = getattr(response, "choices", None)
        if not choices:
            raise ValueError("Writer provider returned no choices")
        content = choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Writer provider returned no text")
        if len(content) > MAX_CHAPTER_CHARACTERS:
            raise ValueError("Generated chapter exceeds length limit")
        return content.strip()
