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

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.database.models import FileKind, ItemCategory, Menu
from app.locales.messages import t


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
            (cx - self._px(34), y1 + self._px(62), cx + self._px(34), y1 + self._px(130)),
            outline=(80, 62, 43),
            width=self._px(0.7),
        )
        heart_font = self._font(52, serif=True)
        self._center_text(draw, "♡", cx, y1 + self._px(84), heart_font, gold)
        text_font = self._font(20, serif=True)
        self._multiline_center(
            draw,
            t("back_text", menu.customer.language),
            cx,
            y1 + self._px(155),
            text_font,
            self.CREAM,
            max_width=self._px(150),
        )
        small = self._font(10)
        self._center_text(draw, "FOOD_PORN • PERSONAL MENU", cx, y2 - self._px(35), small, self.MUTED)

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
            t("cover_title", menu.customer.language),
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
            if item.category
            in (
                ItemCategory.MAIN,
                ItemCategory.APPETIZER,
                ItemCategory.DESSERT,
                ItemCategory.SALAD,
            )
        ]
        drinks = [item for item in menu.items if item.category == ItemCategory.DRINK]
        self._draw_food_grid(page, left, left_items, menu)
        self._draw_right_panel(page, right, drinks, menu)

    def _draw_food_grid(self, page: Image.Image, box: tuple[int, int, int, int], items: list, menu: Menu) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1, x2, y2 = box
        pad = self._px(8)
        header_h = self._px(25)
        draw.text(
            (x1 + pad, y1 + self._px(7)),
            t("cover_title", menu.customer.language),
            font=self._font(23, serif=True, bold=True),
            fill=self.GOLD,
        )
        draw.line(
            (x1 + self._px(113), y1 + self._px(17), x2 - pad, y1 + self._px(17)),
            fill=(113, 86, 53),
            width=max(2, self._px(0.35)),
        )

        gap = self._px(4.5)
        grid_x = x1 + pad
        grid_y = y1 + header_h
        grid_w = x2 - x1 - 2 * pad
        grid_h = y2 - grid_y - pad
        card_w = (grid_w - 2 * gap) // 3
        row_gap = self._px(3)
        row_h = (grid_h - 2 * row_gap) // 3
        section_order = (
            (ItemCategory.MAIN, "main_section"),
            (ItemCategory.APPETIZER, "appetizer_section"),
            (ItemCategory.DESSERT, "dessert_section"),
        )

        for row, (category, section_key) in enumerate(section_order):
            row_y = grid_y + row * (row_h + row_gap)
            label = t(section_key, menu.customer.language).upper()
            label_font = self._font(7.5, bold=True)
            draw.text((grid_x, row_y), label, font=label_font, fill=self.GOLD)
            label_width = draw.textbbox((0, 0), label, font=label_font)[2]
            draw.line(
                (
                    grid_x + label_width + self._px(4),
                    row_y + self._px(3.8),
                    x2 - pad,
                    row_y + self._px(3.8),
                ),
                fill=(87, 68, 48),
                width=max(1, self._px(0.25)),
            )
            category_items = [item for item in items if item.category == category]
            photo_y = row_y + self._px(8)
            for col, item in enumerate(category_items[:3]):
                bx = grid_x + col * (card_w + gap)
                card = (bx, photo_y, bx + card_w, row_y + row_h)
                self._draw_item_card(page, card, item, menu, compact=True)

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

        picture = self._safe_item_image(item.image_path, width, height)
        picture = ImageEnhance.Color(picture).enhance(0.94)
        picture = ImageEnhance.Contrast(picture).enhance(1.07)

        caption_h = self._px(18 if compact else 22)
        caption = Image.new("RGBA", picture.size, (0, 0, 0, 0))
        caption_draw = ImageDraw.Draw(caption)
        gradient_start = max(0, height - caption_h * 2)
        for y in range(gradient_start, height):
            progress = (y - gradient_start) / max(1, height - gradient_start - 1)
            alpha = int(18 + 220 * (progress**1.5))
            caption_draw.line((0, y, width, y), fill=(12, 10, 9, alpha))
        picture = Image.alpha_composite(picture.convert("RGBA"), caption).convert("RGB")

        mask = Image.new("L", picture.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        page.paste(picture, (x1, y1), mask)

        draw = ImageDraw.Draw(page)
        draw.rounded_rectangle(
            box,
            radius=radius,
            outline=(132, 98, 57),
            width=max(2, self._px(0.35)),
        )
        self._fit_text(
            draw,
            item.title,
            (x1 + self._px(4), y2 - caption_h, x2 - self._px(4), y2 - self._px(3)),
            self._font(9.2 if compact else 9.8, serif=True, bold=True),
            self.CREAM,
            max_lines=2,
        )

    def _draw_right_panel(self, page: Image.Image, box: tuple[int, int, int, int], drinks: list, menu: Menu) -> None:
        draw = ImageDraw.Draw(page)
        x1, y1, x2, y2 = box
        pad = self._px(8)
        draw.text(
            (x1 + pad, y1 + self._px(7)),
            t("drink_section", menu.customer.language).upper(),
            font=self._font(20, serif=True, bold=True),
            fill=self.GOLD,
        )
        draw.line(
            (x1 + self._px(83), y1 + self._px(17), x2 - pad, y1 + self._px(17)),
            fill=(113, 86, 53),
            width=max(2, self._px(0.35)),
        )

        grid_y = y1 + self._px(28)
        gap = self._px(4)
        columns = 3
        visible_drinks = drinks[:3]
        card_w = (x2 - x1 - 2 * pad - (columns - 1) * gap) // columns
        card_h = self._px(70)
        for index, item in enumerate(visible_drinks):
            row, col = divmod(index, columns)
            bx = x1 + pad + col * (card_w + gap)
            by = grid_y + row * (card_h + gap)
            self._draw_item_card(page, (bx, by, bx + card_w, by + card_h), item, menu)

        drink_rows = max(1, (len(visible_drinks) + columns - 1) // columns)
        lower_y = grid_y + drink_rows * card_h + drink_rows * gap + self._px(5)

        # Use the second photograph as a borderless background. It reaches the
        # trim edges and fades into the dark page instead of looking pasted on.
        background_top = max(y1, lower_y - self._px(28))
        background_box = (x1, background_top, x2, y2)
        spread_photo = self._cover_image(
            Path(menu.spread_photo_path),
            background_box[2] - background_box[0],
            background_box[3] - background_box[1],
            centering=(0.62, 0.5),
        )
        spread_photo = ImageEnhance.Color(spread_photo).enhance(0.88)
        spread_photo = ImageEnhance.Contrast(spread_photo).enhance(1.06)

        shade = Image.new("RGBA", spread_photo.size, (0, 0, 0, 0))
        shade_draw = ImageDraw.Draw(shade)
        shade_w, shade_h = spread_photo.size
        for x in range(shade_w):
            progress = x / max(1, shade_w - 1)
            alpha = int(225 * ((1 - progress) ** 1.7) + 22)
            shade_draw.line((x, 0, x, shade_h), fill=(16, 13, 12, alpha))
        spread_photo = Image.alpha_composite(spread_photo.convert("RGBA"), shade).convert("RGB")

        # Fade the actual photo pixels into the page; darkening alone leaves a
        # visible horizontal seam at the top edge.
        blend_mask = Image.new("L", spread_photo.size, 0)
        blend_draw = ImageDraw.Draw(blend_mask)
        fade_height = min(shade_h, self._px(70))
        for y in range(shade_h):
            progress = min(1.0, y / max(1, fade_height - 1))
            smooth = progress * progress * (3 - 2 * progress)
            blend_draw.line((0, y, shade_w, y), fill=int(255 * smooth))
        page.paste(spread_photo, (background_box[0], background_box[1]), blend_mask)

        draw = ImageDraw.Draw(page)
        rx = x1 + self._px(15)
        rules_right = x1 + self._px(126)
        ry = lower_y + self._px(10)
        draw.line(
            (rx, ry - self._px(2), rx, y2 - self._px(27)),
            fill=(130, 96, 55),
            width=max(2, self._px(0.45)),
        )
        rx += self._px(8)
        draw.text((rx, ry), t("payment_rules", menu.customer.language), font=self._font(15, serif=True, bold=True), fill=self.GOLD)
        ry += self._px(23)
        for icon, key in zip(("♡", "♥", "♡", "♥"), ("payment_1", "payment_2", "payment_3", "payment_4"), strict=True):
            draw.text((rx, ry), icon, font=self._font(14, serif=True), fill=self.GOLD)
            self._fit_text(
                draw,
                t(key, menu.customer.language),
                (rx + self._px(12), ry, rules_right, ry + self._px(18)),
                self._font(8.2, serif=True),
                self.CREAM,
                max_lines=2,
            )
            ry += self._px(21)

        caption_box = (rx, y2 - self._px(39), rules_right, y2 - self._px(8))
        self._fit_text(
            draw,
            t("made_with_love", menu.customer.language),
            caption_box,
            self._font(11, serif=True, italic=True),
            self.GOLD,
            max_lines=2,
        )

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

    def _safe_item_image(self, path: str | None, width: int, height: int) -> Image.Image:
        if path and Path(path).is_file():
            try:
                return self._cover_image(Path(path), width, height)
            except OSError:
                pass
        fallback = Image.new("RGB", (width, height), (44, 36, 31))
        draw = ImageDraw.Draw(fallback)
        for y in range(height):
            progress = y / max(1, height - 1)
            color = (
                int(38 + 14 * progress),
                int(31 + 8 * progress),
                int(28 + 4 * progress),
            )
            draw.line((0, y, width, y), fill=color)
        self._center_text(
            draw,
            "—",
            width // 2,
            height // 2 - self._px(4),
            self._font(16, serif=True),
            self.GOLD,
        )
        return fallback.filter(ImageFilter.GaussianBlur(radius=0.2))

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
            Path(f"C:/Windows/Fonts/{'georgiab' if serif and bold else 'georgia' if serif else 'arial'}.ttf"),
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
