"""Opt-in, text-only illustration provider for Little Legend.

No child photos, portrait references or URLs are sent to the provider.
Callers must enforce consent, cost limits and ownership before invoking this adapter.
"""
from __future__ import annotations

import base64
import binascii
import os
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from app.little_legend.illustrated_pdf import MAX_IMAGE_BYTES
from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.story_graph import SceneNode


class IllustrationSettings(BaseModel):
    enabled: bool = False
    model: str = Field(default="gpt-image-1-mini", min_length=1, max_length=100)
    size: str = "1024x1024"
    quality: str = "low"

    def model_post_init(self, __context: Any) -> None:
        if self.size not in {"1024x1024", "1024x1536", "1536x1024"}:
            raise ValueError("Unsupported illustration size")
        if self.quality not in {"low", "medium", "high"}:
            raise ValueError("Unsupported illustration quality")


class OpenAIIllustrationProvider:
    """Generates an original illustration for one scene, with no photo inputs."""

    def __init__(self, *, client: Any, settings: IllustrationSettings) -> None:
        if not settings.enabled:
            raise PermissionError("Illustration generation is disabled")
        self._client = client
        self._settings = settings

    async def generate_scene(
        self, *, scene: SceneNode, hero: str, style: str,
        continuity: str = "",
    ) -> bytes:
        result = await self.generate_scene_with_receipt(
            scene=scene, hero=hero, style=style, continuity=continuity,
        )
        return result.data

    async def generate_scene_with_receipt(
        self, *, scene: SceneNode, hero: str, style: str,
        continuity: str = "",
    ) -> IllustrationProviderResult:
        """Return bytes plus receipt only with operator-verified per-image price."""
        if not hero.strip() or not style.strip() or not scene.summary.strip():
            raise ValueError("Scene, hero and style are required")
        if len(continuity) > 1200:
            raise ValueError("Continuity notes are oversized")
        prompt = (
            "Original child-friendly storybook illustration. "
            "No typography, logos, watermarks, copyrighted characters, "
            "photorealistic child likeness or identifiable real person. "
            "Do not depict a real child's face. "
            f"Visual style: {style[:120]}. "
            f"Fictional protagonist name: {hero[:100]}. "
            f"Scene: {scene.summary[:2000]}. "
            f"Character continuity notes (fictional only): {continuity}. "
            "Keep main subjects away from the page trim and gutter."
        )
        response = await self._client.images.generate(
            model=self._settings.model,
            prompt=prompt,
            size=self._settings.size,
            quality=self._settings.quality,
            n=1,
        )
        images = getattr(response, "data", None)
        if not images or len(images) != 1:
            raise ValueError("Illustration provider returned no image")
        encoded = getattr(images[0], "b64_json", None)
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Illustration provider returned no image bytes")
        if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 4:
            raise ValueError("Illustration exceeds size limit")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Illustration provider returned invalid base64") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Illustration exceeds size limit")
        reference = getattr(response, "id", None)
        configured_price = os.getenv("LL_ILLUSTRATION_USD_PER_IMAGE")
        if configured_price is None or not reference:
            return IllustrationProviderResult(data=raw)
        try:
            price = Decimal(configured_price)
        except InvalidOperation as exc:
            raise ValueError("Invalid configured illustration price") from exc
        if not price.is_finite() or price < 0:
            raise ValueError("Invalid configured illustration price")
        amount = int(
            (price * 1_000_000).to_integral_value(rounding=ROUND_CEILING)
        )
        return IllustrationProviderResult(
            data=raw, actual_micro_usd=amount,
            provider_reference=reference,
        )
