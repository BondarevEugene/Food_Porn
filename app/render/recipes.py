"""Premium A4 recipe companion: printable shopping list and illustrated recipes.

No HTML, browser, rasterized text or image generation is required. ReportLab
produces searchable Unicode copy, with one consistent Food_Porn brand system.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as PDFImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.menu_wizard import display_dish_title

INK = colors.HexColor("#2F2826")
GOLD = colors.HexColor("#A17A45")
MUTED = colors.HexColor("#736C67")
CREAM = colors.HexColor("#FBF9F6")
LINE = colors.HexColor("#E8E0D6")


def _register_font() -> str:
    family = "FoodPornDejaVu"
    if family not in pdfmetrics.getRegisteredFontNames():
        fonts = (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        )
        path = next((p for p in fonts if p.is_file()), None)
        if path is None:
            raise RuntimeError("Install a Unicode TrueType font to render the recipe sheet")
        pdfmetrics.registerFont(TTFont(family, str(path)))
    return family


def _labels(language: str) -> dict[str, str]:
    translations = {
        "uk": {
            "title": "Рецепти до вашої особливої вечері",
            "shopping": "Список покупок",
            "recipes": "Рецепти",
            "note": "Позначте те, що вже є вдома",
            "servings": "Порцій", "difficulty": "Складність",
            "equipment": "Обладнання", "allergens": "Алергени",
            "produce": "Овочі та фрукти", "meat_fish": "М'ясо та риба",
            "dairy": "Молочне", "bakery": "Випічка", "pantry": "Бакалія",
            "drinks": "Напої", "frozen": "Заморожене", "other": "Інше",
            "breakfast": "Сніданок", "lunch": "Обід", "dinner": "Вечеря",
            "easy": "Легка", "medium": "Середня", "hard": "Складна",
        },
        "ru": {
            "title": "Рецепты для особенного вечера",
            "shopping": "Список покупок",
            "recipes": "Рецепты",
            "note": "Отметьте то, что уже есть дома",
            "servings": "Порций", "difficulty": "Сложность",
            "equipment": "Оборудование", "allergens": "Аллергены",
            "produce": "Овощи и фрукты", "meat_fish": "Мясо и рыба",
            "dairy": "Молочное", "bakery": "Выпечка", "pantry": "Бакалея",
            "drinks": "Напитки", "frozen": "Замороженное", "other": "Другое",
            "breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин",
            "easy": "Легко", "medium": "Средняя", "hard": "Сложно",
        },
        "en": {
            "title": "Recipes for a special evening",
            "shopping": "Shopping list", "recipes": "Recipes",
            "note": "Check what you already have at home",
            "servings": "Servings", "difficulty": "Difficulty",
            "equipment": "Equipment", "allergens": "Allergens",
            "produce": "Produce", "meat_fish": "Meat & fish",
            "dairy": "Dairy", "bakery": "Bakery", "pantry": "Pantry",
            "drinks": "Drinks", "frozen": "Frozen", "other": "Other",
            "breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner",
            "easy": "Easy", "medium": "Medium", "hard": "Hard",
        },
    }
    return translations.get(language.lower(), translations["ru"])


def _footer(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 16 * mm, width - 20 * mm, 16 * mm)
    canvas.setFillColor(GOLD)
    canvas.setFont("FoodPornDejaVu", 8)
    canvas.drawString(20 * mm, 11 * mm, "FOOD_PORN  /  RECIPES")
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 20 * mm, 11 * mm, f"{doc.page}")
    canvas.restoreState()


def _ordered_recipes(details: dict, meal_plan: list[tuple[str, str]] | None):
    ordered: list[tuple[str | None, str, dict]] = []
    included: set[str] = set()
    for slot, dish in meal_plan or []:
        info = details.get(dish)
        if isinstance(info, dict) and dish not in included:
            ordered.append((slot, dish, info))
            included.add(dish)
    for dish, info in details.items():
        if isinstance(info, dict) and dish not in included:
            ordered.append((None, dish, info))
    return ordered


def render_recipe_sheet(
    destination: Path,
    details: dict,
    shopping_list: list[str],
    language: str = "uk",
    *,
    shopping_sections: dict[str, list[dict]] | None = None,
    meal_plan: list[tuple[str, str]] | None = None,
    dish_images: dict[str, str] | None = None,
) -> Path:
    font = _register_font()
    destination.parent.mkdir(parents=True, exist_ok=True)
    labels = _labels(str(language))
    title = ParagraphStyle(
        "fp_title", fontName=font, fontSize=17, leading=25,
        alignment=TA_CENTER, textColor=INK, spaceAfter=10,
    )
    section = ParagraphStyle(
        "fp_section", fontName=font, fontSize=12, leading=18,
        textColor=GOLD, spaceBefore=12, spaceAfter=7,
    )
    heading = ParagraphStyle(
        "fp_heading", fontName=font, fontSize=12, leading=18,
        textColor=INK, spaceBefore=7, spaceAfter=5,
    )
    body = ParagraphStyle(
        "fp_body", fontName=font, fontSize=8.5, leading=13,
        textColor=INK, spaceAfter=3,
    )
    muted = ParagraphStyle(
        "fp_muted", parent=body, fontSize=8, textColor=MUTED,
    )
    story = [
        Spacer(1, 7 * mm),
        Paragraph("FOOD_PORN  ·  THE DINNER EDITION", muted),
        Paragraph(escape(labels["title"]), title),
        Paragraph(escape(labels["shopping"]), section),
        Paragraph(escape(labels["note"]), muted),
        Spacer(1, 2 * mm),
    ]
    if shopping_sections:
        for aisle, items in shopping_sections.items():
            if not items:
                continue
            story.append(Paragraph(escape(labels.get(aisle, aisle)), section))
            for item in items:
                amount = " ".join(filter(None, (
                    str(item.get("amount") or ""), str(item.get("unit") or ""),
                )))
                row = f"{item.get('name', '')}  {amount}".strip()
                story.append(Paragraph("□  " + escape(row), body))
    else:
        for item in shopping_list:
            story.append(Paragraph(
                "□  " + escape(str(item).removeprefix("• ").strip()), body,
            ))

    recipes = _ordered_recipes(details, meal_plan)
    if recipes:
        story.extend((PageBreak(), Paragraph(escape(labels["recipes"]), title)))
    previous_slot = None
    for slot, dish, info in recipes:
        # "other" is an internal grouping, not a printable heading.
        if slot in ("breakfast", "lunch", "dinner") and slot != previous_slot:
            story.append(Paragraph(escape(labels[slot]), section))
        previous_slot = slot
        name = display_dish_title(dish)
        header = [Paragraph(escape(name), heading)]
        path = (dish_images or {}).get(dish)
        if path and Path(path).is_file():
            image = PDFImage(path, width=34 * mm, height=26 * mm, kind="proportional")
            image.hAlign = "LEFT"
            header = [Table(
                [[image, Paragraph(escape(name), heading)]],
                colWidths=(40 * mm, 120 * mm),
                style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]),
            )]

        ingredients = [
            Paragraph("•  " + escape(str(value)), body)
            for value in info.get("ingredients", [])
        ]
        meta = []
        for field in ("servings", "difficulty", "equipment", "allergens"):
            value = info.get(field)
            if not value:
                continue
            if field == "difficulty":
                value = labels.get(str(value).lower(), value)
            if isinstance(value, (list, tuple)):
                value = ", ".join(map(str, value))
            meta.append(f"{labels[field]}: {value}")

        lines = list(header)
        if meta:
            lines.append(Paragraph(escape("  ·  ".join(meta)), muted))
        lines.extend(ingredients)
        recipe = str(info.get("recipe", "")).strip()
        if recipe:
            # ReportLab paragraphs need <br/> to preserve each numbered step.
            lines.append(Spacer(1, 3 * mm))
            lines.append(Paragraph(
                escape(recipe).replace("\n", "<br/>"), body,
            ))
        for substitute in info.get("substitutions", []) or []:
            lines.append(Paragraph("↔  " + escape(str(substitute)), muted))
        # Keep the heading and first ingredient together, but allow long
        # recipes to flow to the next page rather than overflowing A4.
        story.append(KeepTogether(lines[:min(3, len(lines))]))
        story.extend(lines[min(3, len(lines)):])
        story.append(Spacer(1, 7 * mm))

    doc = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=20 * mm,
        leftMargin=20 * mm, topMargin=19 * mm, bottomMargin=22 * mm,
        title="Food Porn · Premium Recipes",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination
