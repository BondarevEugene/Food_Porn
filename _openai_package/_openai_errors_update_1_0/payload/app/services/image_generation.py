"""Generate one real, validated photograph for each menu item."""

from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.services.openai_errors import (
    AIProblem,
    OpenAIServiceError,
    invalid_response,
    request_openai,
    reset_openai_access,
)

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """An item has no usable image; never publish a finished menu."""


class RetryableImageGenerationError(ImageGenerationError):
    pass


class QuotaExhaustedError(ImageGenerationError, OpenAIServiceError):
    def __init__(self, message: str = "Image API credits exhausted", code: str = "credit_balance_exhausted", *, problem: AIProblem | None = None):
        OpenAIServiceError.__init__(self, problem or AIProblem("quota", code))


class ImageGenerationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=180)
        self._quota_blocked_until = 0.0

    async def close(self) -> None:
        await self.http_client.aclose()
        await self.openai_client.close()

    @staticmethod
    def _openai_error_code(error: Any) -> str | None:
        body = getattr(error, "body", error)
        if isinstance(body, dict):
            details = body.get("error", body)
            if isinstance(details, dict):
                return details.get("code") or details.get("type")
        return getattr(error, "code", None) or getattr(error, "type", None)

    def allow_quota_probe(self) -> None:
        self._quota_blocked_until = 0.0
        if hasattr(self, "settings"):
            reset_openai_access(self.settings.openai_api_key.get_secret_value())

    async def generate(self, prompt: str, destination: Path) -> Path:
        # A demo placeholder must never become a paid PDF or a VIP delivery.
        if self.settings.use_mock_images:
            raise ImageGenerationError("USE_MOCK_IMAGES=true: выключите режим заглушек в .env для настоящих блюд")
        if self.settings.openai_api_key.get_secret_value() in ("", "replace_me"):
            raise OpenAIServiceError(AIProblem("auth", "missing_api_key"))

        try:
            data = await self._request_image(prompt)
            return self._save_verified_jpeg(data, destination)
        except OpenAIServiceError as exc:
            if exc.problem.kind == "quota":
                raise QuotaExhaustedError(problem=exc.problem) from None
            raise
        except (UnidentifiedImageError, ValueError):
            raise invalid_response() from None
        except OSError:
            raise OpenAIServiceError(AIProblem("storage", "local_storage_error")) from None

    async def _request_image(self, prompt: str, destination: Path | None = None) -> bytes | Path:
        # GPT Image returns b64_json; its URL is often null. Preserve the exact
        # dish name and styling instructions already composed by PromptBuilder.
        async def generate_image():
            return await self.openai_client.images.generate(
                model=self.settings.openai_image_model, prompt=prompt,
                size=self.settings.openai_image_size,
                quality=self.settings.openai_image_quality, n=1,
            )
        response = await request_openai(
            generate_image, api_key=self.settings.openai_api_key.get_secret_value(),
            operation="menu_image", image_request=True, attempts=self.settings.image_retries,
            quota_cooldown=getattr(self.settings, "openai_quota_cooldown_seconds", 300),
        )
        if not response.data:
            raise invalid_response()
        image = response.data[0]
        if image.b64_json:
            try:
                payload = base64.b64decode(image.b64_json, validate=True)
            except ValueError:
                raise invalid_response() from None
        elif image.url:
            result = await self.http_client.get(image.url)
            result.raise_for_status()
            payload = result.content
        else:
            raise invalid_response()
        if destination is not None:
            return self._save_verified_jpeg(payload, destination)
        return payload

    @staticmethod
    def _save_verified_jpeg(payload: bytes, destination: Path) -> Path:
        if len(payload) < 1000:
            raise ValueError("Image data is too small")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with Image.open(io.BytesIO(payload)) as source:
                source.load()
                if source.width < 512 or source.height < 512:
                    raise ValueError("Image resolution is too low for print")
                photo = ImageOps.exif_transpose(source).convert("RGB")
                photo.save(temporary, "JPEG", quality=94, subsampling=0)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
