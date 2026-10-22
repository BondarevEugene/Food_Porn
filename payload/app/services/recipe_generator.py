"""
==========================================================
FOOD_PORN

Module: Recipe and Shopping List Service
Layer: Service

Responsibilities:
    - Generate recipes and ingredient lists for menu items via LLM in a single batch request
    - Optimize token usage through centralized payload formatting
    - Smart local analysis fallback for offline/no-quota mode
==========================================================
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import Settings
from app.services.openai_errors import OpenAIServiceError, invalid_response, request_openai

logger = logging.getLogger(__name__)


class RecipeGeneratorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=60)
        self.model = "gpt-4o-mini"

    async def close(self) -> None:
        await self.client.close()

    async def generate_menu_details(self, dishes: list[str], language: str = "uk") -> dict[str, Any]:
        """
        Принимает список названий блюд и возвращает для каждого из них
        ингредиенты с граммовками и пошаговый рецепт за 1 запрос к API.
        Включает каскадный запасной поиск (OpenAI -> Spoonacular -> Smart Local Mock).
        """
        if not dishes:
            return {}

        prompt = (
            f"You are a professional chef and recipe developer.\n"
            f"Language code: {language}.\n"
            f"Given this list of dishes: {json.dumps(dishes, ensure_ascii=False)}.\n\n"
            f"For each dish, provide:\n"
            f"1. 'ingredients': a list of strings containing ingredients with precise quantities (e.g., 'Картопля - 500г').\n"
            f"2. 'recipe': a concise, step-by-step preparation guide.\n\n"
            f"3. 'prep_minutes' and 'cook_minutes': realistic whole-number estimates for one home cook; "
            f"use 0 cook_minutes for uncooked dishes.\n\n"
            f"Return ONLY valid JSON format where keys are exact dish names from the list, like this:\n"
            f'{{\n    "Dish Name": {{\n        "ingredients": ["ing1", "ing2"],\n        "recipe": "Step 1... Step 2...",\n        "prep_minutes": 20, "cook_minutes": 30\n    }}\n}}'
        )

        try:
            async def complete():
                return await self.client.chat.completions.create(
                    model=self.model, messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}, temperature=0.3,
                )
            response = await request_openai(
                complete, api_key=self.settings.openai_api_key.get_secret_value(),
                operation="menu_recipes", attempts=self.settings.image_retries,
                quota_cooldown=self.settings.openai_quota_cooldown_seconds,
            )
            content = response.choices[0].message.content
            details = json.loads(content)
            if not isinstance(details, dict) or any(
                title not in details
                or not isinstance(details[title], dict)
                or not details[title].get("ingredients")
                or not details[title].get("recipe")
                for title in dishes
            ):
                raise ValueError("Recipe response is incomplete")
            return details

        except Exception as exc:
            logger.warning("Recipe generation failed (%s); checking configured fallback", type(exc).__name__)
            key = self.settings.spoonacular_api_key.get_secret_value()
            if not key or key == "replace_me":
                if isinstance(exc, OpenAIServiceError):
                    raise
                if isinstance(exc, (ValueError, TypeError, IndexError, AttributeError)):
                    raise invalid_response() from None
                raise RuntimeError("Recipe unavailable for dish: " + dishes[0]) from None

            fallback_result = {}
            for title in dishes:
                success = False

                # Попытка №2: проверяем реальный источник рецепта, если настроен.
                try:
                    spoonacular_key = self.settings.spoonacular_api_key.get_secret_value()
                    if not spoonacular_key or spoonacular_key == "replace_me":
                        raise RuntimeError("Spoonacular key is not configured")
                    async with httpx.AsyncClient() as client:
                        url = "https://api.spoonacular.com/recipes/complexSearch"
                        params = {
                            "query": title,
                            "number": 1,
                            "addRecipeInformation": "true",
                            "fillIngredients": "true",
                            "apiKey": spoonacular_key
                        }
                        resp = await client.get(url, params=params, timeout=10.0)
                        resp.raise_for_status()
                        data = resp.json()

                        if data.get("results"):
                            recipe_data = data["results"][0]
                            instructions = recipe_data.get("instructions") or recipe_data.get("summary") or "Step 1. Prepare ingredients."
                            instructions = re.sub(r'<[^>]+>', '', instructions)

                            ingredients = [
                                f"{ing.get('name', 'Ingredient').capitalize()} - {round(ing.get('amount', 1), 1)} {ing.get('unit', '')}".strip()
                                for ing in recipe_data.get("extendedIngredients", [])
                            ]
                            if ingredients:
                                fallback_result[title] = {
                                    "ingredients": ingredients,
                                    "recipe": instructions[:1500],
                                    "prep_minutes": 20,
                                    "cook_minutes": max(0, min(int(recipe_data.get("readyInMinutes") or 50) - 20, 180)),
                                }
                                logger.info(f"Recipe '{title}' successfully recovered via Spoonacular.")
                                success = True
                except Exception as sp_exc:
                    logger.warning("Spoonacular fallback failed (%s)", type(sp_exc).__name__)

                # Не продаём сгенерированную заглушку как проверенный рецепт.
                if not success:
                    if isinstance(exc, OpenAIServiceError):
                        raise exc from None
                    raise RuntimeError(f"Recipe unavailable for dish: {title}") from None

            return fallback_result
