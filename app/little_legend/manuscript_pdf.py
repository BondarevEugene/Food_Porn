"""Render the actual manuscript as an A5 editorial book proof.

This is NOT a print-certified edition: no illustrations, bleed, CMYK,
binding imposition or press color profile are supplied.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from app.little_legend.print_renderer import _font
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


def render_manuscript_proof(
    *, title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript,
) -> bytes:
    """Typeset saved chapter prose, without silently substituting outlines."""
    if not title.strip():
        raise ValueError("Book title is required")
    if not manuscript.hero_name.strip():
        raise ValueError("Hero name is required")
    ordered = sorted(graph.nodes, key=lambda node: node.order)
    expected = {node.id for node in ordered}
    actual = {chapter.scene_id for chapter in manuscript.chapters}
    if expected != actual:
        raise ValueError("Manuscript must contain exactly the planned scenes")
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    font = _font()
    output = BytesIO()
    width, height = A5
    doc = BaseDocTemplate(
        output, pagesize=A5, leftMargin=48, rightMargin=42,
        topMargin=52, bottomMargin=52,
        title=title, author="Little Legend · editorial proof",
        pageCompression=1,
    )
    frame = Frame(48, 52, width - 90, height - 104, showBoundary=0)

    def page(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#657089"))
        canvas.drawString(48, height - 30, "LITTLE LEGEND / EDITORIAL PROOF")
        canvas.drawCentredString(width / 2, 27, str(document.page))
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id="book", frames=[frame], onPage=page))
    title_style = ParagraphStyle(
        "BookTitle", fontName=font, fontSize=18, leading=27,
        alignment=TA_CENTER, textColor=colors.HexColor("#26334B"),
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "ChapterTitle", fontName=font, fontSize=13, leading=20,
        textColor=colors.HexColor("#26334B"), spaceAfter=18,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "BookBody", fontName=font, fontSize=10, leading=17,
        spaceAfter=12, allowWidows=0, allowOrphans=0,
    )
    note_style = ParagraphStyle(
        "ProofNote", parent=body_style, fontSize=8, leading=13,
        textColor=colors.HexColor("#657089"),
    )
    flow = [
        Spacer(1, 110),
        Paragraph(escape(title), title_style),
        Paragraph(escape(manuscript.hero_name), title_style),
        Spacer(1, 35),
        Paragraph("РЕДАКЦИОННЫЙ МАКЕТ · НЕ ДЛЯ ТИПОГРАФИИ", note_style),
        PageBreak(),
        Paragraph("Посвящение", title_style),
        Paragraph(escape(dedication or "Эта история — для тебя."), body_style),
        PageBreak(),
    ]
    for node in ordered:
        chapter = chapters[node.id]
        flow.append(Paragraph(
            f"Глава {node.order}. {escape(node.title)}", heading_style,
        ))
        # Empty lines are intentional paragraph breaks; escape all user prose.
        paragraphs = [
            item.strip() for item in chapter.text.splitlines() if item.strip()
        ]
        for paragraph in paragraphs:
            flow.append(Paragraph(escape(paragraph), body_style))
        flow.append(PageBreak())
    flow.extend([
        Paragraph("Редакторская информация", title_style),
        Paragraph(
            "Этот макет содержит полный текст рукописи, но не является "
            "утверждённым типографским оригинал-макетом.", note_style,
        ),
        Paragraph(
            "Финальная публикация требует отдельной проверки текста, "
            "иллюстраций, прав и печатных параметров.", note_style,
        ),
    ])
    doc.build(flow)
    return output.getvalue()
