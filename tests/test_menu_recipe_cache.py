"""Persisted recipe cache prevents unnecessary paid recipe regeneration."""

from types import SimpleNamespace

from app.services.menu_recipe_cache import cached_recipe_details, split_recipe_work


def item(title: str, *, recipe: str | None = "1. Cook", ingredients=None):
    return SimpleNamespace(
        title=title,
        recipe=recipe,
        ingredients=["Rice — 200 g"] if ingredients is None else ingredients,
        prep_minutes=10,
        cook_minutes=15,
        servings=2,
        difficulty="easy",
        equipment=["pan"],
        allergens=[],
        substitutions=[],
        shopping_items=[],
    )


def test_complete_recipe_reused() -> None:
    cached = cached_recipe_details(item("Rice"))
    assert cached is not None
    assert cached["recipe"] == "1. Cook"
    assert cached["ingredients"] == ["Rice — 200 g"]


def test_missing_recipe_requires_generation() -> None:
    cached, missing = split_recipe_work([item("Rice", recipe=None)])
    assert cached == {}
    assert missing == ["Rice"]


def test_empty_ingredients_require_generation() -> None:
    assert cached_recipe_details(item("Rice", ingredients=[])) is None


def test_only_missing_dishes_are_requested() -> None:
    cached, missing = split_recipe_work(
        [item("Rice"), item("Soup", recipe=None), item("—")]
    )
    assert list(cached) == ["Rice"]
    assert missing == ["Soup"]


def test_complete_menu_needs_no_generation() -> None:
    cached, missing = split_recipe_work([item("Rice"), item("Soup")])
    assert len(cached) == 2
    assert missing == []


def test_duplicate_title_with_missing_recipe_regenerates() -> None:
    cached, missing = split_recipe_work([item("Rice"), item("Rice", recipe=None)])
    assert cached == {}
    assert missing == ["Rice"]
