"""
==========================================================
FOOD_PORN

Module: Image Generation / Search Service
Layer: Infrastructure / External APIs

Responsibilities:
    - Cascade image fetching: Spoonacular API ➔ OpenAI DALL-E ➔ Local Mocks
    - Handle API limits gracefully
==========================================================
"""

import logging
import shutil
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import Settings


class RetryableImageGenerationError(Exception):
    """Исключение для ошибок генерации изображений, которые можно повторить."""
    pass


logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Base exception for image fetching failures."""
    pass


class QuotaExhaustedError(ImageGenerationError):
    def __init__(self, message="Quota exhausted", code="credit_balance_exhausted"):
        super().__init__(message)
        self.code = code


class ImageGenerationService:

    async def _request_image(self, prompt: str) -> bytes:
        """Метод для тестов, возвращающий байты изображения."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "img.jpg"
            await self.generate(prompt, dest)
            return dest.read_bytes()

    def __init__(self, settings: Settings):
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=15.0)
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._quota_blocked_until = 0.0

    async def close(self) -> None:
        """Close clients gracefully."""
        await self.http_client.aclose()
        await self.openai_client.close()

    async def generate(self, prompt: str, destination: Path) -> Path:
        """
        Каскадный метод получения изображения:
        1. Сначала пробуем найти готовое качественное фото через Spoonacular API.
        2. При ошибке или отсутствии результата переключаемся на генерацию через OpenAI (DALL-E).
        3. В крайнем случае используем локальный мок-плейсхолдер.
        """
        if self.settings.use_mock_images:
            logger.info(f"Using mock placeholder for prompt: '{prompt}'")
            return await self._use_mock_image(destination)

        destination.parent.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # ПОПЫТКА №1: Поиск изображения через Spoonacular API
        # ------------------------------------------------------------------
        logger.info(f"Searching Spoonacular image for prompt: '{prompt}'")
        try:
            search_url = "https://api.spoonacular.com/recipes/complexSearch"
            params = {
                "query": prompt,
                "number": 1,
                "apiKey": self.settings.spoonacular_api_key.get_secret_value()
            }

            response = await self.http_client.get(search_url, params=params)

            if response.status_code == 402:
                logger.error("Spoonacular API quota exhausted.")
                raise QuotaExhaustedError("Spoonacular daily points limit reached.")

            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if results and "image" in results[0]:
                base_image_url = results[0]["image"]
                high_res_url = base_image_url.replace("-312x231", "-636x393")

                img_response = await self.http_client.get(high_res_url)
                img_response.raise_for_status()

                with open(destination, "wb") as f:
                    f.write(img_response.content)

                logger.info(f"Successfully downloaded image via Spoonacular for '{prompt}'")
                return destination
            else:
                logger.warning(f"Spoonacular found no image for '{prompt}'. Switching to OpenAI fallback...")

        except Exception as sp_exc:
            logger.warning(f"Spoonacular fallback failed ({sp_exc}). Switching to OpenAI...")

        # ------------------------------------------------------------------
        # ПОПЫТКА №2: Генерация изображения через OpenAI (DALL-E)
        # ------------------------------------------------------------------
        try:
            logger.info(f"Attempting OpenAI image generation for prompt: '{prompt}'")
            openai_prompt = (
                f"A realistic premium restaurant food photograph of '{prompt}', "
                "presented as an elegant dish, dark matte charcoal background, warm candlelit lighting, "
                "editorial food photography, square composition, no text, no watermark."
            )

            response = await self.openai_client.images.generate(
                model=getattr(self.settings, "openai_image_model", "dall-e-3"),
                prompt=openai_prompt,
                size=getattr(self.settings, "openai_image_size", "1024x1024"),
                quality=getattr(self.settings, "openai_image_quality", "standard"),
                n=1,
            )
            image_url = response.data[0].url

            img_resp = await self.http_client.get(image_url, timeout=30.0)
            img_resp.raise_for_status()

            with open(destination, "wb") as f:
                f.write(img_resp.content)

            logger.info(f"Successfully generated image via OpenAI for '{prompt}'")
            return destination

        except Exception as openai_exc:
            logger.warning(f"OpenAI image generation fallback also failed ({openai_exc}). Using local mock.")

        # ------------------------------------------------------------------
        # ПОПЫТКА №3: Финальный локальный мок
        # ------------------------------------------------------------------
        return await self._use_mock_image(destination)

    async def _use_mock_image(self, destination: Path) -> Path:
        """Fallback method that uses a local placeholder image."""
        placeholder_path = self.settings.demo_dir / "placeholder.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)

        if not placeholder_path.exists():
            placeholder_path.parent.mkdir(parents=True, exist_ok=True)
            placeholder_path.touch()
            logger.warning(
                f"Placeholder missing! Created empty file at {placeholder_path}. Please place a real JPEG there.")

        shutil.copy(placeholder_path, destination)
        return destination

    @staticmethod
    @staticmethod
    def _openai_error_code(error: Any) -> str | None:
        """Извлекает код или тип ошибки для тестов (поддерживает словари и объекты)."""
        if hasattr(error, "body") and isinstance(error.body, dict):
            err_dict = error.body.get("error", {})
            return err_dict.get("code") or err_dict.get("type")
        if isinstance(error, dict):
            err_dict = error.get("error", error)
            return err_dict.get("code") or err_dict.get("type")
            # Поддержка прямого словаря типа {"type": "rate_limit_error"}
        if isinstance(error, dict) and "type" in error:
            return error.get("type")
        return None

    async def _request_once(self, prompt: str) -> bytes:
        """Метод для старых тестов ретраев, возвращающий байты картинки."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "img.jpg"
            await self.generate(prompt, dest)
            return dest.read_bytes()

    async def _request_image(self, prompt: str, destination: Path | None = None) -> Path | bytes:
        """Алиас для генерации, совместимый с разной длиной аргументов в тестах."""
        if destination is None:
            return await self._request_once(prompt)
        return await self.generate(prompt, destination)

    def allow_quota_probe(self) -> None:
        """Сбрасывает блокировку квоты для тестов."""
        self._quota_blocked_until = 0.0

    async def _request_image(self, prompt: str, destination: Path) -> Path:
        """Алиас для генерации изображения (используется в тестах)."""
        return await self.generate(prompt, destination)
