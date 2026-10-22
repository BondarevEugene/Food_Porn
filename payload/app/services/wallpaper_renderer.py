"""
==========================================================
FOOD_PORN

Module: AI-Powered Fine Art Renderer
Layer: Service (OpenAI)
==========================================================
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from openai import AsyncOpenAI

from app.services.openai_errors import invalid_response, request_openai

logger = logging.getLogger(__name__)


# =========================
# Exceptions
# =========================
class WallpaperRenderError(Exception):
    """Base renderer exception."""


class WallpaperBillingError(WallpaperRenderError):
    """API billing / credits issue."""


class WallpaperRateLimitError(WallpaperRenderError):
    """OpenAI rate limit issue."""


class WallpaperConfigError(WallpaperRenderError):
    """Configuration issue."""


# =========================
# DTO
# =========================
@dataclass(slots=True)
class RenderedWallpaper:
    path: Path
    file_name: str
    prompt: str
    model: str
    size: str
    revised_prompt: str | None = None


# =========================
# Renderer
# =========================
class WallpaperRenderer:
    """
    Async image renderer for OpenAI Images API.
    """

    BILLING_ERROR_CODES = {
        "credit_balance_exhausted",
        "insufficient_quota",
        "billing_hard_limit_reached",
        "billing_not_active",
    }

    RATE_LIMIT_ERROR_CODES = {
        "rate_limit_exceeded",
        "requests_per_minute_exceeded",
        "tokens_per_minute_exceeded",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-image-1.5",
        output_dir: str | Path = "storage/wallpapers",
        max_attempts: int = 3,
        base_delay_seconds: float = 2.0,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise WallpaperConfigError(
                "OPENAI_API_KEY is not set. "
                "Set it in environment variables or pass api_key explicitly."
            )

        self.model = model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            max_retries=0,
            timeout=timeout_seconds,
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        file_name: str | None = None,
    ) -> RenderedWallpaper:
        """
        Generate image and save it to disk.
        """
        if not prompt or not prompt.strip():
            raise WallpaperRenderError("Prompt is empty.")

        final_file_name = file_name or f"{uuid.uuid4().hex}.png"
        final_path = self.output_dir / final_file_name

        response = await request_openai(
            lambda: self.client.images.generate(model=self.model, prompt=prompt, size=size),
            api_key=self.api_key, operation="legacy_wallpaper_image",
            attempts=self.max_attempts, image_request=True,
        )
        return await self._save_response(response, final_path, prompt, size)

    async def edit_image(
        self,
        *,
        image_path: Path | str,
        prompt: str,
        size: str = "1024x1024",
        file_name: str | None = None,
    ) -> RenderedWallpaper:
        """
        Edit/variation of user's photo using OpenAI Images Edit API,
        preserving identity and applying Old Money aesthetic.
        """
        if not prompt or not prompt.strip():
            raise WallpaperRenderError("Prompt is empty.")

        img_path = Path(image_path)
        if not img_path.exists():
            raise WallpaperRenderError(f"Source image not found at {img_path}")

        final_file_name = file_name or f"{uuid.uuid4().hex}.png"
        final_path = self.output_dir / final_file_name

        async def edit():
            with img_path.open("rb") as img_file:
                return await self.client.images.edit(
                    model=self.model, image=img_file, prompt=prompt, size=size,
                )
        response = await request_openai(
            edit, api_key=self.api_key, operation="legacy_wallpaper_edit",
            attempts=self.max_attempts, image_request=True,
        )
        return await self._save_response(response, final_path, prompt, size)

    async def _save_response(self, response, path: Path, prompt: str, size: str) -> RenderedWallpaper:
        if not response.data:
            raise invalid_response()
        item = response.data[0]
        if getattr(item, "b64_json", None):
            try:
                image_bytes = base64.b64decode(item.b64_json, validate=True)
            except ValueError:
                raise invalid_response() from None
        elif getattr(item, "url", None):
            async with aiohttp.ClientSession() as session:
                async with session.get(str(item.url)) as resp:
                    if resp.status != 200:
                        raise invalid_response()
                    image_bytes = await resp.read()
        else:
            raise invalid_response()
        path.write_bytes(image_bytes)
        return RenderedWallpaper(
            path=path, file_name=path.name, prompt=prompt, model=self.model,
            size=size, revised_prompt=getattr(item, "revised_prompt", None),
        )

    async def close(self) -> None:
        await self.client.close()


# Алиас для обратной совместимости
AIFineArtRenderer = WallpaperRenderer
