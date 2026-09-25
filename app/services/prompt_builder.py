"""
==========================================================
FOOD_PORN

Module: Food Image Prompt Builder
Layer: Service

Responsibilities:
    - Build deterministic prompts for every menu category
    - Maintain one visual identity across generated dishes
    - Prevent text, people, logos, and packaging in food images
==========================================================
"""

from app.database.models import ItemCategory, MenuItem

CATEGORY_HINTS = {
    ItemCategory.MAIN: "a complete plated main course",
    ItemCategory.APPETIZER: "an elegant small appetizer course",
    ItemCategory.DESSERT: "an elegant plated restaurant dessert",
    ItemCategory.SALAD: "an elegant freshly prepared salad",
    ItemCategory.SOUP: "a refined restaurant soup served in a deep bowl with rich steam",
    ItemCategory.DRINK: "a refined drink in appropriate premium glassware",
}


class PromptBuilder:
    def build(self, item: MenuItem) -> str:
        subject = CATEGORY_HINTS[item.category]
        return (
            f"Create a realistic premium restaurant food photograph of {item.title!r}, "
            f"presented as {subject}. One single serving, centered composition, three-quarter "
            "camera angle, dark matte charcoal background, warm candlelit amber rim light, "
            "subtle copper and gold accents, appetizing natural texture, consistent luxury "
            "romantic dinner-menu visual identity, enough negative space around the plate, "
            "sharp subject, editorial food photography. No people, no hands, no packaging, "
            "no typography, no letters, no logo, no watermark, no border, square composition."
        )
