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

logger = logging.getLogger(__name__)


class RecipeGeneratorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self.model = "gpt-4o-mini"

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
            f"Return ONLY valid JSON format where keys are exact dish names from the list, like this:\n"
            f'{{\n    "Dish Name": {{\n        "ingredients": ["ing1", "ing2"],\n        "recipe": "Step 1... Step 2..."\n    }}\n}}'
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
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
            logger.error(f"Failed to generate recipes via LLM ({exc}). Switching to fallback chain...")

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
                                    "recipe": instructions[:1500]
                                }
                                logger.info(f"Recipe '{title}' successfully recovered via Spoonacular.")
                                success = True
                except Exception as sp_exc:
                    logger.warning(f"Spoonacular fallback failed for '{title}' ({sp_exc}).")

                # Не продаём сгенерированную заглушку как проверенный рецепт.
                if not success:
                    raise RuntimeError(f"Recipe unavailable for dish: {title}") from exc

            return fallback_result
