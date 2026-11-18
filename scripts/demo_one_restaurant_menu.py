"""Produce one reproducible A3 menu from the 50 art directions.

Run: python -m scripts.demo_one_restaurant_menu
Output: storage/demo_restaurant/featured/999/
Uses existing local demo dishes and photos; no AI or network calls.
"""
from __future__ import annotations

import runpy
from pathlib import Path

from app.services.menu_art_directions import choose_direction


def main() -> None:
    sample = runpy.run_module("scripts.demo_render", run_name="food_porn_demo_data")
    menu = sample["menu"]
    menu.visual_style = "color"
    menu.design_seed = "restaurant-edition-featured-v1"
    direction = choose_direction(menu.visual_style, menu.design_seed)
    menu.design_preset = direction.code
    output = sample["BookletRenderer"](Path("storage/demo_restaurant/featured")).render(menu)
    print(f"Preset: {direction.code} — {direction.title}")
    print(f"Art brief: {direction.prompt()}")
    print(f"PDF: {output.print_pdf}")
    print(f"Outside preview: {output.outside_preview}")
    print(f"Inside preview: {output.inside_preview}")


if __name__ == "__main__":
    main()
