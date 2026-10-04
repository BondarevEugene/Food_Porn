"""A lightweight, saved cooking plan for the Mini App.

The order of dishes is editorial. Durations are estimates supplied with the
recipe (or conservative defaults), never a claim that food is ready on time.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

SERVE_ORDER = {"appetizer": 0, "salad": 1, "soup": 2, "main": 3, "dessert": 4, "drink": 5}
DEFAULT_MINUTES = {
    "appetizer": (20, 5), "salad": (15, 0), "soup": (25, 45),
    "main": (25, 40), "dessert": (30, 35), "drink": (10, 0),
}


def _minutes(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if 0 <= value <= 240 else default


def build_evening_plan(items: list[Any], details: dict[str, Any],
                       shopping_list: list[str], language: str) -> dict[str, Any]:
    """Keep the customer names and real recipe text; omit empty placeholders."""
    dishes = []
    for item in items:
        if item.title == "—" or item.title not in details:
            continue
        category = getattr(item.category, "value", item.category)
        category = str(category)
        info = details[item.title]
        if not isinstance(info, dict) or not info.get("recipe") or not info.get("ingredients"):
            raise ValueError(f"Recipe missing for {item.title}")
        prep, cook = DEFAULT_MINUTES.get(category, (20, 30))
        dishes.append({
            "title": item.title,
            "category": category,
            "ingredients": [str(i) for i in info["ingredients"]],
            "recipe": str(info["recipe"]),
            "prep_minutes": _minutes(info.get("prep_minutes"), prep),
            "cook_minutes": _minutes(info.get("cook_minutes"), cook),
            "position": int(item.position or 0),
        })
    if not dishes:
        raise ValueError("No finished dishes for the evening plan")
    return {
        "version": 1,
        "language": language,
        "shopping": [str(value) for value in shopping_list],
        "serve": sorted(dishes, key=lambda d: (SERVE_ORDER.get(d["category"], 9), d["position"])),
        "prepare": sorted(dishes, key=lambda d: (-(d["prep_minutes"] + d["cook_minutes"]),
                                                    SERVE_ORDER.get(d["category"], 9), d["position"])),
    }


def save_evening_plan(path: Path, plan: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path
