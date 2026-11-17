"""Render three A3 restaurant-theme previews using the existing demo dish list.

Usage: python -m scripts.demo_restaurant_themes
Output: storage/demo_restaurant/{dark,light,color}/999/
No Telegram, database connection, payment, or OpenAI call is required.
"""
from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    # Reuse the repository's existing deterministic demo customer, photos
    # and dish list; all three designs must show exactly the same content.
    sample = runpy.run_module("scripts.demo_render", run_name="food_porn_demo_data")
    menu = sample["menu"]
    renderer_class = sample["BookletRenderer"]
    for style in ("dark", "light", "color"):
        menu.design_style = style
        output = renderer_class(Path("storage/demo_restaurant") / style).render(menu)
        print(f"{style}: {output.print_pdf}")
        print(f"{style} outside: {output.outside_preview}")
        print(f"{style} inside: {output.inside_preview}")


if __name__ == "__main__":
    main()
