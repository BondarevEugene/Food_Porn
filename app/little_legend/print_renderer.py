"""Little Legend print-layout proof: A5 book interior, not a press-ready edition."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from app.little_legend.story_graph import StoryGraph

FONT_PATHS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)


def _font() -> str:
    for path in FONT_PATHS:
        if path.is_file():
            if "LittleLegendUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("LittleLegendUnicode", str(path)))
            return "LittleLegendUnicode"
    raise RuntimeError("Unicode font missing: install fonts-dejavu-core")


def render_print_proof(
    *, title: str, hero: str, dedication: str, city: str,
    graph: StoryGraph,
) -> bytes:
    """Render an A5 editorial proof with page numbers and Cyrillic support.

    This is deliberately marked PROOF: scene summaries are not final prose,
    illustrations are not embedded, and bleed/color management are not certified.
    """
    font = _font()
    output = BytesIO()
    width, height = A5
    doc = BaseDocTemplate(
        output, pagesize=A5, leftMargin=49, rightMargin=39,
        topMargin=50, bottomMargin=50,
        title=title, author="Little Legend · редакционный макет",
        pageCompression=1,
    )
    frame = Frame(49, 50, width - 88, height - 100, showBoundary=0)
    def page(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#68738A"))
        canvas.drawCentredString(width / 2, 27, str(document.page))
        canvas.drawString(49, height - 29, "LITTLE LEGEND  /  РЕДАКЦИОННЫЙ МАКЕТ")
        canvas.restoreState()
    doc.addPageTemplates(PageTemplate(id="book", frames=[frame], onPage=page))
    heading = ParagraphStyle(
        "Heading", fontName=font, fontSize=18, leading=26,
        textColor=colors.HexColor("#26334B"), alignment=TA_CENTER,
        spaceAfter=18,
    )
    subheading = ParagraphStyle(
        "Scene", fontName=font, fontSize=13, leading=19,
        textColor=colors.HexColor("#26334B"), spaceAfter=12,
    )
    body = ParagraphStyle(
        "Body", fontName=font, fontSize=10, leading=16, spaceAfter=12,
    )
    small = ParagraphStyle(
        "Small", parent=body, fontSize=8, leading=13,
        textColor=colors.HexColor("#657089"),
    )
    content = [
        Spacer(1, 110),
        Paragraph(escape(title), heading),
        Paragraph(f"История о герое по имени {escape(hero)}", body),
        Spacer(1, 50),
        Paragraph("ПРОБНЫЙ МАКЕТ · НЕ ДЛЯ ТИПОГРАФИИ", small),
        PageBreak(),
        Paragraph("Посвящение", heading),
        Paragraph(escape(dedication or "Эта история — для тебя."), body),
        PageBreak(),
    ]
    for node in sorted(graph.nodes, key=lambda n: n.order):
        content.append(KeepTogether([
            Paragraph(f"Глава {node.order}. {escape(node.title)}", subheading),
            Paragraph(escape(node.summary or "Сцена ещё не написана."), body),
            Paragraph("Редакторская цель: " + escape(node.goal), small),
        ]))
        content.append(PageBreak())
    content.extend([
        Paragraph("Сведения об издании", heading),
        Paragraph("Город: " + escape(city or "Не указан"), body),
        Paragraph("Статус: редакционный макет, не опубликовано", small),
        Paragraph("Автор и иллюстратор указываются после утверждения материалов.", small),
    ])
    doc.build(content)
    return output.getvalue()
