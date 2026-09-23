"""
==========================================================
FOOD_PORN

Module: Recipe and Shopping List Service
Layer: Service

Responsibilities:
    - Generate recipes and ingredient lists for menu items via LLM in a single batch request
    - Optimize token usage through centralized payload formatting
==========================================================
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from openai import AsyncOpenAI
import httpx
import re

from app.config import Settings

logger = logging.getLogger(__name__)


class RecipeGeneratorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Используем экономичную и быструю модель для пакетных текстовых задач
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())  # <-- Исправлено
        self.model = "gpt-4o-mini"

    async def generate_menu_details(self, dishes: List[str], language: str = "uk") -> Dict[str, Any]:
        """
        Принимает список названий блюд и возвращает для каждого из них
        ингредиенты с граммовками и пошаговый рецепт за 1 запрос к API.
        Включает каскадный запасной поиск (OpenAI -> Spoonacular -> Mock).
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
            return json.loads(content)

        except Exception as exc:
            logger.error(f"Failed to generate recipes via LLM ({exc}). Switching to fallback chain...")

            fallback_result = {}
            for title in dishes:
                try:
                    # Попытка №2: Ищем через бесплатный Spoonacular API
                    async with httpx.AsyncClient() as client:
                        url = "https://api.spoonacular.com/recipes/complexSearch"
                        params = {
                            "query": title,
                            "number": 1,
                            "addRecipeInformation": "true",
                            "fillIngredients": "true",
                            "apiKey": self.settings.spoonacular_api_key.get_secret_value()
                        }
                        resp = await client.get(url, params=params, timeout=10.0)
                        resp.raise_for_status()
                        data = resp.json()

                        if not data.get("results"):
                            raise ValueError("Recipe not found in Spoonacular")

                        recipe_data = data["results"][0]
                        instructions = recipe_data.get("instructions") or recipe_data.get(
                            "summary") or "Step 1. Prepare ingredients. Step 2. Cook well."
                        instructions = re.sub(r'<[^>]+>', '', instructions)

                        ingredients = [
                            f"{ing.get('name', 'Ingredient').capitalize()} - {round(ing.get('amount', 1), 1)} {ing.get('unit', '')}".strip()
                            for ing in recipe_data.get("extendedIngredients", [])
                        ]
                        if not ingredients:
                            ingredients = ["Main ingredient - 500g", "Spices - to taste"]

                        fallback_result[title] = {
                            "ingredients": ingredients,
                            "recipe": instructions[:1500]
                        }
                        logger.info(f"Recipe '{title}' successfully recovered via Spoonacular.")

                except Exception as sp_exc:
                    # Попытка №3: Экстренный локальный мок (гарантия успешного рендера PDF)
                    logger.warning(f"Spoonacular fallback failed for '{title}' ({sp_exc}). Using default mock.")
                    fallback_result[title] = {
                        "ingredients": ["Основной продукт - 500г", "Специи - по вкусу", "Оливковое масло - 2 ст.л."],
                        "recipe": f"1. Подготовить все необходимые ингредиенты для блюда '{title}'.\n2. Тщательно обработать продукты и обжарить до золотистой корочки.\n3. Подавать к столу в горячем виде с любимым соусом."
                    }

            return fallback_result