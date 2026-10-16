"""Printable recipe and shopping list for a paid menu."""
from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer


def render_recipe_sheet(
    destination: Path,
    details: dict,
    shopping_list: list[str],
    language: str = "uk",
    *,
    shopping_sections: dict[str, list[dict]] | None = None,
) -> Path:
    """Render exact user dish names, ingredients and instructions to A4 PDF."""
    font_name = "FoodPornDejaVu"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        fonts = (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        )
        available = next((path for path in fonts if path.is_file()), None)
        if available is None:
            raise RuntimeError("Install a Unicode TrueType font to render the recipe sheet")
        pdfmetrics.registerFont(TTFont(font_name, str(available)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    title = ParagraphStyle("title", fontName=font_name, fontSize=15, leading=21, alignment=TA_CENTER)
    heading = ParagraphStyle("heading", fontName=font_name, fontSize=11, leading=16, spaceBefore=12)
    body = ParagraphStyle("body", fontName=font_name, fontSize=9, leading=14, spaceAfter=4)
    is_uk = language.lower() == "uk"
    story = [Paragraph("Рецепти та список покупок" if is_uk else "Рецепты и список покупок", title), Spacer(1, 8 * mm)]
    story.append(Paragraph("Список покупок" if is_uk else "Список покупок", heading))
    aisle_names = {
        "produce": "Овочі та фрукти" if is_uk else "Овощи и фрукты",
        "meat_fish": "М'ясо та риба" if is_uk else "Мясо и рыба",
        "dairy": "Молочне" if is_uk else "Молочное",
        "bakery": "Випічка" if is_uk else "Выпечка",
        "pantry": "Бакалія" if is_uk else "Бакалея",
        "drinks": "Напої" if is_uk else "Напитки",
        "frozen": "Заморожене" if is_uk else "Замороженное",
        "other": "Інше" if is_uk else "Другое",
    }
    if shopping_sections:
        for aisle, items in shopping_sections.items():
            story.append(Paragraph(escape(aisle_names.get(aisle, aisle)), heading))
            for item in items:
                amount = " ".join(filter(None, (str(item.get("amount") or ""), str(item.get("unit") or ""))))
                pantry = " · є в коморі?" if is_uk and item.get("pantry") else " · есть дома?" if item.get("pantry") else ""
                story.append(Paragraph(
                    "• " + escape(f"{item.get('name', '')} {amount}{pantry}".strip()), body
                ))
    else:
        for ingredient in shopping_list:
            story.append(Paragraph("• " + escape(str(ingredient).removeprefix("• ")), body))
    for dish, info in details.items():
        if not isinstance(info, dict):
            continue
        lines = [Paragraph(escape(str(dish)), heading)]
        for ingredient in info.get("ingredients", []):
            lines.append(Paragraph("• " + escape(str(ingredient)), body))
        facts = []
        if info.get("servings"):
            facts.append(("Порцій" if is_uk else "Порций") + f": {info['servings']}")
        if info.get("difficulty"):
            facts.append(("Складність" if is_uk else "Сложность") + f": {info['difficulty']}")
        if info.get("equipment"):
            facts.append(("Обладнання" if is_uk else "Оборудование") + ": " + ", ".join(map(str, info["equipment"])))
        if info.get("allergens"):
            facts.append(("Алергени" if is_uk else "Аллергены") + ": " + ", ".join(map(str, info["allergens"])))
        if facts:
            lines.append(Paragraph(escape(" · ".join(facts)), body))
        recipe = str(info.get("recipe", "")).strip()
        if recipe:
            lines.append(Paragraph(escape(recipe).replace("\n", "<br/>"), body))
        for substitute in info.get("substitutions", []):
            lines.append(Paragraph("↔ " + escape(str(substitute)), body))
        story.append(KeepTogether(lines[:2]) if len(lines) > 1 else lines[0])
        story.extend(lines[2:] if len(lines) > 1 else [])
    doc = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title="Food Porn Recipes",
    )
    doc.build(story)
    return destination
