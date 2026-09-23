"""
==========================================================
FOOD_PORN

Module: Image Generation / Search Service
Layer: Infrastructure / External APIs

Responsibilities:
    - Search and fetch high-quality food images using Spoonacular API
    - Provide fallback local placeholder images for development (Mocks)
    - Handle API limits gracefully
==========================================================
"""

import logging
import shutil
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Base exception for image fetching failures."""
    pass


class QuotaExhaustedError(ImageGenerationError):
    """Raised when Spoonacular/OpenAI API credits are exhausted."""
    pass


class ImageGenerationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        """Close the async HTTP client gracefully."""
        await self.http_client.aclose()

    async def generate(self, prompt: str, destination: Path) -> Path:
        """
        Fetches an image based on the prompt (recipe name) and saves it to destination.
        Uses Mock if enabled, otherwise calls Spoonacular API.
        """
        if self.settings.use_mock_images:
            logger.info(f"Using mock placeholder for prompt: '{prompt}'")
            return await self._use_mock_image(destination)

        logger.info(f"Searching Spoonacular image for prompt: '{prompt}'")
        try:
            # 1. Запрос к Spoonacular (ищем рецепт с картинкой по названию блюда)
            search_url = "https://api.spoonacular.com/recipes/complexSearch"
            params = {
                "query": prompt,
                "number": 1,
                # Безопасно извлекаем строку из SecretStr
                "apiKey": self.settings.spoonacular_api_key.get_secret_value()
            }

            response = await self.http_client.get(search_url, params=params)

            if response.status_code == 402:
                logger.error("Spoonacular API quota exhausted.")
                raise QuotaExhaustedError("Spoonacular daily points limit reached.")

            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results or "image" not in results[0]:
                logger.warning(f"Spoonacular found no image for '{prompt}'. Falling back to mock.")
                return await self._use_mock_image(destination)

            base_image_url = results[0]["image"]

            # 2. Улучшение качества. Spoonacular отдает -312x231.jpg по умолчанию.
            high_res_url = base_image_url.replace("-312x231", "-636x393")

            # 3. Скачиваем картинку
            img_response = await self.http_client.get(high_res_url)
            img_response.raise_for_status()

            # 4. Сохраняем на диск
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "wb") as f:
                f.write(img_response.content)

            logger.info(f"Successfully downloaded image for '{prompt}'")
            return destination

        except httpx.HTTPError as exc:
            logger.error(f"HTTP Error while fetching image: {exc}")
            raise ImageGenerationError(f"Network or API error: {exc}")
        except Exception as exc:
            if isinstance(exc, QuotaExhaustedError):
                raise
            logger.error(f"Unexpected error in image fetching: {exc}")
            raise ImageGenerationError(f"Unexpected error: {exc}")

    async def _use_mock_image(self, destination: Path) -> Path:
        """Fallback method that uses a local placeholder image."""
        placeholder_path = self.settings.demo_dir / "placeholder.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)

        if not placeholder_path.exists():
            placeholder_path.parent.mkdir(parents=True, exist_ok=True)
            placeholder_path.touch()
            logger.warning(f"Placeholder missing! Created empty file at {placeholder_path}. Please place a real JPEG there.")

        shutil.copy(placeholder_path, destination)
        return destination
