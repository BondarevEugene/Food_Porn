"""Reuse complete persisted recipes on menu pipeline retries."""

from app.database.models import MenuItem


def cached_recipe_details(item: MenuItem) -> dict | None:
    """Return the persisted recipe only when required content is complete."""
    if not item.ingredients or not item.recipe or not item.recipe.strip():
        return None
    return {
        "ingredients": list(item.ingredients),
        "recipe": item.recipe,
        "prep_minutes": item.prep_minutes or 0,
        "cook_minutes": item.cook_minutes or 0,
        "servings": item.servings or 2,
        "difficulty": item.difficulty or "medium",
        "equipment": list(item.equipment or []),
        "allergens": list(item.allergens or []),
        "substitutions": list(item.substitutions or []),
        "shopping_items": list(item.shopping_items or []),
    }


def split_recipe_work(items: list[MenuItem]) -> tuple[dict[str, dict], list[str]]:
    """Partition existing recipes and missing dishes, preserving original titles."""
    cached: dict[str, dict] = {}
    missing: list[str] = []
    for item in items:
        if item.title == "—":
            continue
        details = cached_recipe_details(item)
        if details is None:
            if item.title not in missing:
                missing.append(item.title)
        else:
            cached[item.title] = details
    for title in missing:
        cached.pop(title, None)
    return cached, missing
