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
from app.database.session import async_session_maker
from app.services.cost_tracker import log_openai_response

logger = logging.getLogger(__name__)


class RecipeGeneratorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self.model = settings.recipe_model

    async def generate_menu_details(
        self,
        dishes: list[str],
        language: str = "uk",
        *,
        user_id: int = 0,
        order_id: str | int | None = None,
    ) -> dict[str, Any]:
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
            f"1. 'ingredients': display-ready strings with precise quantities for exactly 2 servings.\n"
            f"2. 'shopping_items': objects with name, amount (number), unit, aisle "
            f"(produce, meat_fish, dairy, bakery, pantry, drinks, frozen, other), and pantry (boolean).\n"
            f"3. 'recipe': numbered, concise step-by-step instructions with food-safety cues.\n"
            f"4. 'prep_minutes' and 'cook_minutes': realistic whole-number estimates for one home cook; "
            f"use 0 cook_minutes for uncooked dishes.\n"
            f"5. 'servings': 2, 'difficulty': easy|medium|advanced, 'equipment': string list, "
            f"'allergens': string list, 'substitutions': practical string list.\n\n"
            f"Return ONLY valid JSON format where keys are exact dish names from the list, like this:\n"
            f'{{\n    "Dish Name": {{\n        "ingredients": ["Potato — 500 g"],\n'
            f'        "shopping_items": [{{"name":"Potato","amount":500,"unit":"g","aisle":"produce","pantry":false}}],\n'
            f'        "recipe": "1. Prepare...\\n2. Cook...", "prep_minutes": 20, "cook_minutes": 30,\n'
            f'        "servings": 2, "difficulty": "medium", "equipment": ["pan"],\n'
            f'        "allergens": [], "substitutions": []\n    }}\n}}'
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            try:
                async with async_session_maker() as session:
                    await log_openai_response(
                        session,
                        settings=self.settings,
                        response=response,
                        user_id=user_id,
                        model_name=self.model,
                        operation="menu_recipes_batch",
                        product_type="menu",
                        order_id=order_id,
                        details={"dish_count": len(dishes), "language": str(language)},
                    )
            except Exception:
                logger.exception("Failed to persist recipe generation cost")
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
            for title in dishes:
                item = details[title]
                item.setdefault("servings", 2)
                item.setdefault("difficulty", "medium")
                item.setdefault("equipment", [])
                item.setdefault("allergens", [])
                item.setdefault("substitutions", [])
                item.setdefault("shopping_items", [])
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
                                    "recipe": instructions[:1500],
                                    "prep_minutes": 20,
                                    "cook_minutes": max(0, min(int(recipe_data.get("readyInMinutes") or 50) - 20, 180)),
                                    "servings": 2,
                                    "difficulty": "medium",
                                    "equipment": [],
                                    "allergens": [],
                                    "substitutions": [],
                                    "shopping_items": [],
                                }
                                logger.info(f"Recipe '{title}' successfully recovered via Spoonacular.")
                                success = True
                except Exception as sp_exc:
                    logger.warning(f"Spoonacular fallback failed for '{title}' ({sp_exc}).")

                # Не продаём сгенерированную заглушку как проверенный рецепт.
                if not success:
                    raise RuntimeError(f"Recipe unavailable for dish: {title}") from exc

            return fallback_result
