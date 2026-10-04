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
    destination: Path, details: dict, shopping_list: list[str], language: str = "uk"
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
    for ingredient in shopping_list:
        story.append(Paragraph("• " + escape(str(ingredient).removeprefix("• ")), body))
    for dish, info in details.items():
        if not isinstance(info, dict):
            continue
        lines = [Paragraph(escape(str(dish)), heading)]
        for ingredient in info.get("ingredients", []):
            lines.append(Paragraph("• " + escape(str(ingredient)), body))
        recipe = str(info.get("recipe", "")).strip()
        if recipe:
            lines.append(Paragraph(escape(recipe).replace("\n", "<br/>"), body))
        story.append(KeepTogether(lines[:2]) if len(lines) > 1 else lines[0])
        story.extend(lines[2:] if len(lines) > 1 else [])
    doc = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title="Food Porn Recipes",
    )
    doc.build(story)
    return destination
