"""
==========================================================
FOOD_PORN

Module: AI-Powered Fine Art Renderer
Layer: Service (OpenAI)
==========================================================
"""
from __future__ import annotations

import aiohttp
import asyncio
import base64
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

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
    revised_prompt: Optional[str] = None


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
        api_key: Optional[str] = None,
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
        file_name: Optional[str] = None,
    ) -> RenderedWallpaper:
        """
        Generate image and save it to disk.
        """
        if not prompt or not prompt.strip():
            raise WallpaperRenderError("Prompt is empty.")

        final_file_name = file_name or f"{uuid.uuid4().hex}.png"
        final_path = self.output_dir / final_file_name

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.info(
                    "Generating image attempt %s using %s with size %s",
                    attempt,
                    self.model,
                    size,
                )

                response = await self.client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=size,
                )

                item = response.data[0]
                revised_prompt = getattr(item, "revised_prompt", None)

                if getattr(item, "b64_json", None):
                    image_bytes = base64.b64decode(item.b64_json)
                    logger.info("Image received via b64_json directly.")

                elif getattr(item, "url", None):
                    image_url = str(item.url)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            if resp.status != 200:
                                raise WallpaperRenderError(f"Не вдалося завантажити зображення. Статус: {resp.status}")
                            image_bytes = await resp.read()
                    logger.info("Image downloaded successfully via URL.")

                else:
                    debug_data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    raise WallpaperRenderError(f"Невідомий формат відповіді від API: {debug_data}")

                final_path.write_bytes(image_bytes)
                logger.info("Image successfully generated: %s", final_path)

                return RenderedWallpaper(
                    path=final_path,
                    file_name=final_file_name,
                    prompt=prompt,
                    model=self.model,
                    size=size,
                    revised_prompt=revised_prompt,
                )

            except RateLimitError as exc:
                error_code, error_message = self._extract_error_info(exc)
                logger.warning("OpenAI 429 on attempt %s/%s", attempt, self.max_attempts)
                if error_code in self.BILLING_ERROR_CODES:
                    raise WallpaperBillingError("OpenAI billing error / balance exhausted.") from exc
                if attempt >= self.max_attempts:
                    raise WallpaperRateLimitError("OpenAI rate limit exceeded.") from exc
                await self._sleep_before_retry(attempt)

            except Exception as exc:
                logger.exception("Unexpected wallpaper generation error: %s", str(exc))
                raise WallpaperRenderError(f"Unexpected wallpaper generation error: {str(exc)}") from exc

        raise WallpaperRenderError("Image generation failed unexpectedly.")

    async def edit_image(
        self,
        *,
        image_path: Path | str,
        prompt: str,
        size: str = "1024x1024",
        file_name: Optional[str] = None,
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

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.info(
                    "Editing image attempt %s using model %s based on user photo",
                    attempt,
                    self.model,
                )

                # Открываем подготовленное фото пользователя для отправки в API редактора
                # Використовуємо вашу активну модель замість застарілої dall-e-2
                with open(img_path, "rb") as img_file:
                    response = await self.client.images.edit(
                        model=self.model,
                        image=img_file,
                        prompt=prompt,
                        size=size,
                    )

                item = response.data[0]
                revised_prompt = getattr(item, "revised_prompt", None)

                if getattr(item, "b64_json", None):
                    image_bytes = base64.b64decode(item.b64_json)
                elif getattr(item, "url", None):
                    image_url = str(item.url)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            if resp.status != 200:
                                raise WallpaperRenderError(f"Не вдалося завантажити відредаговане зображення. Статус: {resp.status}")
                            image_bytes = await resp.read()
                else:
                    debug_data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    raise WallpaperRenderError(f"Невідомий формат відповіді від Edit API: {debug_data}")

                final_path.write_bytes(image_bytes)
                logger.info("Image successfully edited and saved: %s", final_path)

                return RenderedWallpaper(
                    path=final_path,
                    file_name=final_file_name,
                    prompt=prompt,
                    model=self.model,
                    size=size,
                    revised_prompt=revised_prompt,
                )

            except RateLimitError as exc:
                logger.warning("OpenAI 429 on edit attempt %s/%s", attempt, self.max_attempts)
                if attempt >= self.max_attempts:
                    raise WallpaperRateLimitError("OpenAI rate limit exceeded during edit.") from exc
                await self._sleep_before_retry(attempt)

            except Exception as exc:
                logger.exception("Unexpected image editing error: %s", str(exc))
                raise WallpaperRenderError(f"Image edit error: {str(exc)}") from exc

        raise WallpaperRenderError("Image editing failed unexpectedly.")

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.base_delay_seconds * (2 ** (attempt - 1))
        logger.info("Sleeping %.1f seconds before retry...", delay)
        await asyncio.sleep(delay)

    def _extract_error_info(self, exc: Exception) -> tuple[Optional[str], str]:
        error_code = None
        error_message = str(exc)
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                error_code = err.get("code") or err.get("type")
                error_message = err.get("message", error_message)
        return error_code, error_message


# Алиас для обратной совместимости
AIFineArtRenderer = WallpaperRenderer
