"""
==========================================================
FOOD_PORN

Module: A3 Booklet Renderer
Layer: Rendering

Responsibilities:
    - Compose outside and inside folded A3 artwork
    - Blend customer and food photography into the design
    - Export Telegram previews and print-ready PDF files
==========================================================
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.database.models import FileKind, ItemCategory, Language, Menu
from app.locales.messages import t
from app.services.menu_wizard import (
    MEAL_FULL_DAY,
    display_dish_title,
)


@dataclass(frozen=True)
class RenderedFiles:
    outside_preview: Path
    inside_preview: Path
    print_pdf: Path

    def as_mapping(self) -> dict[FileKind, Path]:
        return {
            FileKind.PREVIEW_OUTSIDE: self.outside_preview,
            FileKind.PREVIEW_INSIDE: self.inside_preview,
            FileKind.PRINT_PDF: self.print_pdf,
        }


def menu_render_snapshot(menu: Menu) -> SimpleNamespace:
    """Freeze ORM values on the async side before sending the PDF job to a thread.

    A renderer must never cause SQLAlchemy lazy loading or DB IO from the
    Pillow/ReportLab worker thread.
    """
    customer = menu.customer
    return SimpleNamespace(
        id=menu.id,
        cover_photo_path=menu.cover_photo_path,
        spread_photo_path=menu.spread_photo_path,
        meal_period=menu.meal_period,
        customer=SimpleNamespace(
            name=customer.name,
            language=customer.language,
        ),
        items=[
            SimpleNamespace(
                id=item.id,
                title=item.title,
                category=item.category,
                position=item.position,
                image_path=item.image_path,
                meal_slot=item.meal_slot,
            )
            for item in menu.items
        ],
    )


class BookletRenderer:
    DPI = 300
    TRIM_W_MM = 420
    TRIM_H_MM = 297
    BLEED_MM = 3

    BG = (20, 17, 17)
    PANEL = (31, 27, 26)
    GOLD = (214, 171, 92)
    CREAM = (244, 232, 211)
    MUTED = (182, 169, 151)

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        self.bleed = self._px(self.BLEED_MM)
        self.trim_w = self._px(self.TRIM_W_MM)
        self.trim_h = self._px(self.TRIM_H_MM)
        self.page_w = self.trim_w + 2 * self.bleed
        self.page_h = self.trim_h + 2 * self.bleed
        self.panel_w = self.trim_w // 2

    def render(self, menu: Menu) -> RenderedFiles:
        if not menu.cover_photo_path or not menu.spread_photo_path:
            raise ValueError("Both customer photos are required")
        directory = self.output_root / str(menu.id)
        directory.mkdir(parents=True, exist_ok=True)

        outside = self._new_page()
        inside = self._new_page()
        self._draw_outside(outside, menu)
        self._draw_inside(inside, menu)
        self._draw_print_marks(outside)
        self._draw_print_marks(inside)

        outside_print = directory / "outside_cmyk.jpg"
        inside_print = directory / "inside_cmyk.jpg"
        outside.convert("CMYK").save(outside_print, "JPEG", quality=96, subsampling=0, dpi=(300, 300))
        inside.convert("CMYK").save(inside_print, "JPEG", quality=96, subsampling=0, dpi=(300, 300))

        outside_preview = directory / "preview_outside.jpg"
        inside_preview = directory / "preview_inside.jpg"
        self._save_preview(outside, outside_preview)
        self._save_preview(inside, inside_preview)

        pdf_path = directory / f"food_porn_menu_{menu.id}_A3_print.pdf"
        self._write_pdf(pdf_path, outside_print, inside_print, menu.id)
        return RenderedFiles(outside_preview, inside_preview, pdf_path)

    def _new_page(self) -> Image.Image:
        page = Image.new("RGB", (self.page_w, self.page_h), self.BG)
        draw = ImageDraw.Draw(page)
        # Subtle warm speckle pattern for a tactile print feel.
        step = max(16, self._px(1.8))
        for y in range(0, self.page_h, step):
            offset = (y // step % 2) * (step // 2)
            for x in range(offset, self.page_w, step):
                draw.point((x, y), fill=(27, 23, 22))
        return page

    @staticmethod
    def _menu_title(menu: Menu) -> str:
        language = getattr(getattr(menu, "customer", None), "language", Language.RU)
        language = getattr(language, "value", language)
        if getattr(menu, "meal_period", None) == MEAL_FULL_DAY:
            return {
                "uk": "МЕНЮ НА ДЕНЬ",
                "ru": "МЕНЮ НА ДЕНЬ",
                "en": "DAILY MENU",
            }.get(str(language), "МЕНЮ НА ДЕНЬ")
        if getattr(menu, "meal_period", None) == "breakfast":
            return {
                "uk": "МЕНЮ СНІДАНКІВ",
                "ru": "МЕНЮ ЗАВТРАКОВ",
                "en": "BREAKFAST MENU",
            }.get(str(language), "МЕНЮ ЗАВТРАКОВ")
        return t("cover_title", menu.customer.language)

    def _draw_outside(self, page: Image.Image, menu: Menu) -> None:
        x0, y0 = self.bleed, self.bleed
        left = (x0, y0, x0 + self.panel_w, y0 + self.trim_h)
        right = (x0 + self.panel_w, y0, x0 + self.trim_w, y0 + self.trim_h)

        draw = ImageDraw.Draw(page)
        draw.rectangle(left, fill=self.PANEL)
        self._draw_back_cover(page, left, menu)
        self._draw_cover(page, right, menu)

    def _draw_back_cover(self, page: Image.Image, box: tuple[int, int, int, int], menu: Menu) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1, x2, y2 = box
        cx = (x1 + x2) // 2
        gold = self.GOLD
        draw.ellipse(
            (cx - self._px(32), y1 + self._px(28), cx + self._px(32), y1 + self._px(92)),
            outline=(80, 62, 43),
            width=self._px(0.7),
        )
        self._center_text(draw, "♡", cx, y1 + self._px(47), self._font(39, serif=True), gold)
        draw.line((cx-self._px(19), y1+self._px(109), cx+self._px(19), y1+self._px(109)),
                  fill=self.GOLD, width=max(2, self._px(.25)))
        self._fit_text(draw, t("love_letter", menu.customer.language),
                       (x1+self._px(25), y1+self._px(125),
                        x2-self._px(25), y1+self._px(212)),
                       self._font(15.5, serif=True, italic=True), self.CREAM, max_lines=12)
        quote_y = y1 + self._px(220)
        draw.line((cx-self._px(31), quote_y, cx+self._px(31), quote_y),
                  fill=(101, 82, 56), width=max(2, self._px(.25)))
        self._fit_text(draw, "“" + t("classic_quote", menu.customer.language) + "”",
                       (x1+self._px(25), quote_y+self._px(7), x2-self._px(25), quote_y+self._px(37)),
                       self._font(11, serif=True, italic=True), self.GOLD, max_lines=3)
        self._fit_text(draw, t("classic_author", menu.customer.language),
                       (x1+self._px(25), quote_y+self._px(42), x2-self._px(25), quote_y+self._px(55)),
                       self._font(9, serif=True), self.MUTED)
        customer_name = getattr(menu.customer, "name", "Любимый")
        self._center_text(draw, f"Сделано с любовью для тебя ✦ {customer_name}", cx, y2-self._px(15),
                          self._font(9.5, serif=True), self.MUTED)

    def _draw_cover(self, page: Image.Image, box: tuple[int, int, int, int], menu: Menu) -> None:
        width = box[2] - box[0]
        height = box[3] - box[1]
        photo = self._cover_image(
            Path(menu.cover_photo_path),
            width,
            height,
            centering=(0.6, 0.5),
        )
        photo = ImageEnhance.Color(photo).enhance(0.86)
        photo = ImageEnhance.Contrast(photo).enhance(1.08)

        # The cover photograph is the page itself, not a separate photo card.
        # The dark left side holds the title while the portrait remains visible.
        shade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shade_draw = ImageDraw.Draw(shade)
        for x in range(width):
            progress = x / max(1, width - 1)
            alpha = int(205 - 155 * progress)
            shade_draw.line((x, 0, x, height), fill=(12, 10, 10, alpha))
        photo = Image.alpha_composite(photo.convert("RGBA"), shade).convert("RGB")
        page.paste(photo, (box[0], box[1]))

        draw = ImageDraw.Draw(page)
        text_x = box[0] + self._px(14)
        text_right = box[0] + self._px(125)
        title_font = self._font(38, serif=True, bold=True)
        script_font = self._font(30, serif=True, italic=True)
        sub_font = self._font(18, serif=True)
        self._fit_text(
            draw,
            self._menu_title(menu),
            (text_x, box[1] + self._px(38), text_right, box[1] + self._px(83)),
            title_font,
            self.GOLD,
            max_lines=2,
        )
        line_y = box[1] + self._px(104)
        draw.line((text_x, line_y, text_x + self._px(38), line_y), fill=self.GOLD, width=max(2, self._px(0.35)))
        draw.text((text_x + self._px(44), line_y - self._px(9)), "♡", font=self._font(17, serif=True), fill=self.GOLD)
        draw.line(
            (text_x + self._px(59), line_y, text_x + self._px(97), line_y),
            fill=self.GOLD,
            width=max(2, self._px(0.35)),
        )
        draw.text((text_x, box[1] + self._px(112)), t("cover_subtitle", menu.customer.language), font=script_font, fill=self.GOLD)
        self._fit_text(draw, t("cover_whisper", menu.customer.language),
                       (text_x, box[1]+self._px(160), text_right, box[1]+self._px(211)),
                       self._font(12, serif=True, italic=True), self.CREAM, max_lines=3)
        draw.text((text_x, box[3] - self._px(28)), menu.customer.name, font=sub_font, fill=self.CREAM)

    def _draw_inside(self, page: Image.Image, menu: Menu) -> None:
        x0, y0 = self.bleed, self.bleed
        left = (x0, y0, x0 + self.panel_w, y0 + self.trim_h)
        right = (x0 + self.panel_w, y0, x0 + self.trim_w, y0 + self.trim_h)
        draw = ImageDraw.Draw(page)
        draw.rectangle(left, fill=self.BG)
        draw.rectangle(right, fill=(24, 21, 20))

        left_items = [
            item
            for item in menu.items
            if item.title != "—" and item.category != ItemCategory.DRINK
        ]
        drinks = [item for item in menu.items if item.title != "—" and item.category == ItemCategory.DRINK]
        if not left_items and not drinks:
            raise ValueError("Menu contains no dishes")
        if len(left_items) > 18 or len(drinks) > 18:
            raise ValueError("Too many menu items for the two-panel print layout")
        self._draw_food_grid(page, left, left_items, menu, drinks=drinks)
        self._draw_right_panel(page, right, menu)

    def _draw_food_grid(self, page: Image.Image, box: tuple[int, int, int, int], items: list, menu: Menu, *, drinks: list | None = None) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1, x2, y2 = box
        pad = self._px(8)
        draw.text(
            (x1 + pad, y1 + self._px(7)),
            self._menu_title(menu),
            font=self._font(23, serif=True, bold=True),
            fill=self.GOLD,
        )
        draw.line(
            (x1 + self._px(113), y1 + self._px(17), x2 - pad, y1 + self._px(17)),
            fill=(113, 86, 53), width=max(2, self._px(0.35)),
        )

        meal_order = {"breakfast": 0, "lunch": 1, "dinner": 2, "other": 3}
        order = {category: index for index, category in enumerate((
            ItemCategory.MAIN, ItemCategory.SOUP, ItemCategory.APPETIZER,
            ItemCategory.SALAD, ItemCategory.DESSERT,
        ))}
        items = sorted(
            items,
            key=lambda item: (
                meal_order.get(getattr(item, "meal_slot", None), 4),
                order.get(item.category, 99),
                item.position,
                item.id or 0,
            ),
        )
        drinks = drinks or []
        columns = 2 if len(items) <= 6 else 3
        rows = (len(items) + columns - 1) // columns
        gap = self._px(4)
        grid_x, grid_y = x1 + pad, y1 + self._px(27)
        # Reserve dedicated space for drinks and the playful, non-monetary bill.
        drinks_rows = (len(drinks) + 2) // 3
        drinks_h = self._px(14 + drinks_rows * 13) if drinks else 0
        bill_h = self._px(59)
        reserved = drinks_h + bill_h + self._px(8)
        grid_w, grid_h = x2 - x1 - 2 * pad, y2 - grid_y - pad - reserved
        card_w = (grid_w - gap * (columns - 1)) // columns
        card_h = min(self._px(156), (grid_h - gap * (rows - 1)) // rows) if rows else 0
        for index, item in enumerate(items):
            row, col = divmod(index, columns)
            bx = grid_x + col * (card_w + gap)
            by = grid_y + row * (card_h + gap)
            self._draw_item_card(page, (bx, by, bx + card_w, by + card_h), item, menu, compact=True)

        section_y = y2 - pad - reserved + self._px(5)
        if drinks:
            self._draw_drinks_section(page, (x1 + pad, section_y, x2 - pad, section_y + drinks_h), drinks, menu)
            section_y += drinks_h
        self._draw_love_bill(page, (x1 + pad, section_y, x2 - pad, y2 - pad), menu)

    def _draw_drinks_section(self, page: Image.Image, box: tuple[int, int, int, int], drinks: list, menu: Menu) -> None:
        x1, y1, x2, _ = box
        draw = ImageDraw.Draw(page)
        lang = str(getattr(menu.customer.language, "value", menu.customer.language) or "ru")
        title = {"uk": "НАПОЇ", "ru": "НАПИТКИ", "en": "DRINKS"}.get(lang, "НАПИТКИ")
        draw.text((x1, y1), title, font=self._font(13, serif=True, bold=True), fill=self.GOLD)
        draw.line((x1 + self._px(48), y1 + self._px(8), x2, y1 + self._px(8)), fill=self.GOLD, width=max(1, self._px(.25)))
        width = (x2 - x1) // 3
        for index, item in enumerate(drinks):
            row, col = divmod(index, 3)
            xx, yy = x1 + col * width, y1 + self._px(14 + row * 13)
            self._fit_text(draw, display_dish_title(item.title),
                           (xx + self._px(1), yy, xx + width - self._px(2), yy + self._px(11)),
                           self._font(9.6, serif=True), self.CREAM, max_lines=2)

    def _draw_love_bill(self, page: Image.Image, box: tuple[int, int, int, int], menu: Menu) -> None:
        """A romantic game printed on the menu, never a real payment method."""
        x1, y1, x2, y2 = box
        draw = ImageDraw.Draw(page)
        lang = str(getattr(menu.customer.language, "value", menu.customer.language) or "ru")
        translations = {
            "uk": ("РАХУНОК ДО СПЛАТИ ♡", ("Ніжний поцілунок", "Теплі обійми", "Щирий комплімент"), ("2 шт.", "3 шт.", "1 шт."), "РАЗОМ: БЕЗЦІННО"),
            "ru": ("СЧЁТ К ОПЛАТЕ ♡", ("Нежный поцелуй", "Тёплые объятия", "Искренний комплимент"), ("2 шт.", "3 шт.", "1 шт."), "ИТОГО: БЕСЦЕННО"),
            "en": ("A BILL OF LOVE ♡", ("A tender kiss", "A warm hug", "A sincere compliment"), ("2", "3", "1"), "TOTAL: PRICELESS"),
        }
        title, labels, amounts, total = translations.get(lang, translations["ru"])
        draw.rounded_rectangle((x1, y1, x2, y2), radius=self._px(4), outline=(132, 98, 57), width=max(2, self._px(.4)))
        self._center_text(draw, title, (x1 + x2) // 2, y1 + self._px(5), self._font(13, serif=True, bold=True), self.GOLD)
        draw.line((x1 + self._px(8), y1 + self._px(17), x2 - self._px(8), y1 + self._px(17)), fill=(113, 86, 53), width=max(1, self._px(.2)))
        for index, (label, amount) in enumerate(zip(labels, amounts, strict=True)):
            yy = y1 + self._px(20 + index * 9)
            draw.text((x1 + self._px(8), yy), label, font=self._font(10.5, serif=True), fill=self.CREAM)
            amount_font = self._font(9.5, serif=True, italic=True)
            amount_w = draw.textbbox((0, 0), amount, font=amount_font)[2]
            draw.text((x2 - self._px(8) - amount_w, yy), amount, font=amount_font, fill=self.GOLD)
        self._center_text(draw, total, (x1 + x2) // 2, y2 - self._px(11), self._font(11, serif=True, bold=True), self.GOLD)

    def _draw_item_card(
        self,
        page: Image.Image,
        box: tuple[int, int, int, int],
        item,
        menu: Menu,
        *,
        compact: bool = False,
    ) -> None:
        x1, y1, x2, y2 = box
        width = x2 - x1
        height = y2 - y1
        radius = self._px(3.2)

        shadow = Image.new("RGBA", (width + self._px(4), height + self._px(4)), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (self._px(2), self._px(2), width, height),
            radius=radius,
            fill=(0, 0, 0, 150),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(self._px(1.6)))
        page.paste(shadow, (x1, y1), shadow)

        # Render directly to the actual photograph viewport. Cropping an image
        # sized for the entire card used to remove the lower half of dishes.
        caption_h = min(height // 3, self._px(23 if compact else 27))
        photo_h = height - caption_h
        picture = self._safe_item_image(item.image_path, width, photo_h)
        picture = ImageEnhance.Color(picture).enhance(1.05)
        picture = ImageEnhance.Contrast(picture).enhance(1.03)
        card = Image.new("RGB", (width, height), (34, 29, 27))
        card.paste(picture, (0, 0))
        mask = Image.new("L", card.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        page.paste(card, (x1, y1), mask)

        draw = ImageDraw.Draw(page)
        draw.rounded_rectangle(box, radius=radius, outline=(132, 98, 57), width=max(2, self._px(0.35)))
        item_title = display_dish_title(item.title)
        self._fit_card_title(
            draw, item_title,
            (x1 + self._px(4), y2 - caption_h + self._px(2), x2 - self._px(4), y2 - self._px(2)),
            compact=compact,
        )

    def _fit_card_title(
        self, draw: ImageDraw.ImageDraw, text: str,
        box: tuple[int, int, int, int], *, compact: bool,
    ) -> None:
        """Fit the complete dish name; never silently truncate a paid menu."""
        x1, y1, x2, y2 = box
        available_width, available_height = x2 - x1, y2 - y1
        if not text.strip():
            return
        for size in (13, 12, 11, 10, 9, 8, 7):
            font = self._font(size if compact else size + 1, serif=True, bold=True)
            lines = []
            current = ""
            for word in text.split():
                trial = f"{current} {word}".strip()
                if draw.textbbox((0, 0), trial, font=font)[2] <= available_width:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            if any(draw.textbbox((0, 0), line, font=font)[2] > available_width for line in lines):
                continue
            line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + self._px(.7)
            if len(lines) * line_height <= available_height:
                yy = y1 + max(0, (available_height - len(lines) * line_height) // 2)
                for line in lines:
                    draw.text((x1, yy), line, font=font, fill=self.CREAM)
                    yy += line_height
                return
        # No ellipsis: fail visibly rather than ship a misleading shortened title.
        raise ValueError(f"Dish title does not fit the card: {text!r}")

    def _draw_right_panel(self, page: Image.Image, box: tuple[int, int, int, int], menu: Menu) -> None:
        """Immersive portrait with soft edges; no food or drink overlays."""
        x1, y1, x2, y2 = box
        draw = ImageDraw.Draw(page)
        lang = str(getattr(menu.customer.language, "value", menu.customer.language) or "ru")
        main = {"uk": "ВАШ ОСОБЛИВИЙ ВЕЧІР", "ru": "ВАШ ОСОБЕННЫЙ ВЕЧЕР", "en": "A SPECIAL EVENING"}.get(lang, "ВАШ ОСОБЕННЫЙ ВЕЧЕР")
        pad = self._px(11)
        draw.text((x1 + pad, y1 + self._px(9)), main, font=self._font(17, serif=True, bold=True), fill=self.GOLD)
        draw.line((x1 + pad, y1 + self._px(23), x2 - pad, y1 + self._px(23)), fill=(126, 95, 66), width=max(2, self._px(.35)))
        photo_top = y1 + self._px(27)
        photo_width, photo_height = x2 - x1, y2 - photo_top
        portrait = self._portrait_contain_image(Path(menu.spread_photo_path), photo_width, photo_height)
        portrait = ImageEnhance.Color(portrait).enhance(.9)
        fade_x, fade_y = max(1, self._px(23)), max(1, self._px(24))
        horizontal = Image.new("L", (photo_width, 1))
        horizontal.putdata([max(0, int(255 * min(1.0, xx / fade_x, (photo_width - 1 - xx) / fade_x))) for xx in range(photo_width)])
        vertical = Image.new("L", (1, photo_height))
        vertical.putdata([max(0, int(240 * min(1.0, yy / fade_y, (photo_height - 1 - yy) / fade_y))) for yy in range(photo_height)])
        alpha = ImageChops.multiply(horizontal.resize((photo_width, photo_height)), vertical.resize((photo_width, photo_height)))
        page.paste(portrait, (x1, photo_top), alpha)

    def _draw_inside_letter(self, page: Image.Image, box: tuple[int, int, int, int], menu: Menu) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1, x2, y2 = box
        draw.line((x1, y1, x1, y2), fill=(130, 96, 55), width=max(2, self._px(.45)))
        draw.text((x1+self._px(8), y1+self._px(2)), t("payment_rules", menu.customer.language),
                  font=self._font(12, serif=True, bold=True), fill=self.GOLD)
        self._fit_text(draw, t("love_letter", menu.customer.language),
                       (x1+self._px(8), y1+self._px(18), x2, y2),
                       self._font(13, serif=True, italic=True), self.CREAM, max_lines=14)

    def _draw_print_marks(self, page: Image.Image) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1 = self.bleed, self.bleed
        x2, y2 = x1 + self.trim_w, y1 + self.trim_h
        mark = max(8, self.bleed - 3)
        color = (20, 20, 20)
        width = max(1, self._px(0.18))
        for x in (x1, x2):
            draw.line((x, 0, x, mark), fill=color, width=width)
            draw.line((x, self.page_h - mark, x, self.page_h), fill=color, width=width)
        for y in (y1, y2):
            draw.line((0, y, mark, y), fill=color, width=width)
            draw.line((self.page_w - mark, y, self.page_w, y), fill=color, width=width)
        fold_x = x1 + self.panel_w
        draw.line((fold_x, 0, fold_x, max(5, self.bleed // 2)), fill=(105, 85, 62), width=width)
        draw.line((fold_x, self.page_h - max(5, self.bleed // 2), fold_x, self.page_h), fill=(105, 85, 62), width=width)

    def _write_pdf(self, path: Path, outside: Path, inside: Path, menu_id: int) -> None:
        page_size = ((self.TRIM_W_MM + 2 * self.BLEED_MM) * mm, (self.TRIM_H_MM + 2 * self.BLEED_MM) * mm)
        pdf = canvas.Canvas(str(path), pagesize=page_size, pageCompression=1)
        pdf.setTitle(f"Food_Porn Menu {menu_id} — A3 Print")
        pdf.setAuthor("Food_Porn Telegram Bot")
        pdf.setSubject("Two-sided A3 folded menu, 3 mm bleed, CMYK artwork")
        for label, artwork in (("OUTSIDE", outside), ("INSIDE", inside)):
            pdf.addPageLabel(0 if label == "OUTSIDE" else 1, style="D", start=1, prefix=f"{label}-")
            pdf.drawImage(str(artwork), 0, 0, width=page_size[0], height=page_size[1], preserveAspectRatio=False, mask=None)
            pdf.showPage()
        pdf.save()

    def _save_preview(self, image: Image.Image, path: Path) -> None:
        preview = image.copy()
        preview.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
        preview.save(path, "JPEG", quality=88, optimize=True)

    def _cover_image(
        self,
        path: Path,
        width: int,
        height: int,
        *,
        centering: tuple[float, float] = (0.5, 0.5),
    ) -> Image.Image:
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            return ImageOps.fit(
                source,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=centering,
            )

    def _portrait_contain_image(self, path: Path, width: int, height: int) -> Image.Image:
        """Keep the full portrait visible, filling spare space with a soft backdrop."""
        with Image.open(path) as original:
            source = ImageOps.exif_transpose(original).convert("RGB")
            backdrop = ImageOps.fit(
                source, (width, height), method=Image.Resampling.LANCZOS
            ).filter(ImageFilter.GaussianBlur(radius=max(8, min(width, height) // 25)))
            backdrop = ImageEnhance.Brightness(backdrop).enhance(0.60)
            foreground = ImageOps.contain(
                source, (width, height), method=Image.Resampling.LANCZOS
            )
            x = (width - foreground.width) // 2
            y = (height - foreground.height) // 2
            backdrop.paste(foreground, (x, y))
            return backdrop

    def _safe_item_image(self, path: str | None, width: int, height: int) -> Image.Image:
        if not path or not Path(path).is_file():
            raise ValueError(f"Dish photograph missing: {path}")
        try:
            return self._cover_image(Path(path), width, height)
        except OSError as exc:
            raise ValueError(f"Dish photograph is unreadable: {path}") from exc

    def _font(self, size_mm: float, *, serif: bool = False, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        size = max(10, self._px(size_mm * 0.36))
        family = "DejaVuSerif" if serif else "DejaVuSans"
        suffix = ""
        if bold and italic:
            suffix = "-BoldItalic"
        elif bold:
            suffix = "-Bold"
        elif italic:
            suffix = "-Italic"
        regular_suffix = "-Bold" if bold else ""
        candidates = [
            Path(f"/usr/share/fonts/truetype/dejavu/{family}{suffix}.ttf"),
            Path(f"/usr/share/fonts/truetype/dejavu/{family}{regular_suffix}.ttf"),
            Path(f"C:/Windows/Fonts/{'georgiab' if serif and bold else 'georgiai' if serif and italic else 'georgia' if serif else 'arial'}.ttf"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        return ImageFont.load_default(size=size)

    def _fit_text(self, draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], font: ImageFont.ImageFont, fill: tuple[int, int, int], max_lines: int = 2) -> None:
        x1, y1, x2, y2 = box
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textbbox((0, 0), trial, font=font)[2] <= x2 - x1:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:max_lines]
        if len(lines) == max_lines and " ".join(lines) != text and lines:
            while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=font)[2] > x2 - x1:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + self._px(1)
        for line in lines:
            if y1 + line_height > y2:
                break
            draw.text((x1, y1), line, font=font, fill=fill)
            y1 += line_height

    def _center_text(self, draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, font: ImageFont.ImageFont, fill: tuple[int, int, int]) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((center_x - (bbox[2] - bbox[0]) // 2, y), text, font=font, fill=fill)

    def _multiline_center(self, draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, font: ImageFont.ImageFont, fill: tuple[int, int, int], max_width: int) -> None:
        average = max(1, draw.textbbox((0, 0), "abcdefghijklmnopqrstuvwxyz", font=font)[2] // 26)
        lines = textwrap.wrap(text, width=max(8, max_width // average))
        for line in lines:
            self._center_text(draw, line, center_x, y, font, fill)
            y += draw.textbbox((0, 0), "Ag", font=font)[3] + self._px(2)

    def _px(self, millimeters: float) -> int:
        return max(1, round(millimeters / 25.4 * self.DPI))
