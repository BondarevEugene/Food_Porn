"""A5 editorial proof combining full prose with explicitly approved images.

Images are supplied in memory by a trusted caller; this module never fetches
URLs, uploads photos, stores files or calls an image generation provider.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from app.little_legend.print_renderer import _font
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000


def _validated_image(raw: bytes) -> Image:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Illustration bytes are missing or oversized")
    try:
        with PILImage.open(BytesIO(raw)) as picture:
            if picture.format not in {"JPEG", "PNG"}:
                raise ValueError("Only JPEG and PNG illustrations are supported")
            width, height = picture.size
            if width < 300 or height < 300 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Illustration dimensions are unsupported")
            picture.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Invalid illustration image") from exc
    available_width = A5[0] - 94
    available_height = 260
    scale = min(available_width / width, available_height / height)
    return Image(BytesIO(raw), width=width * scale, height=height * scale)


def render_illustrated_proof(
    *, title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript, illustrations: dict[str, bytes],
    approved_scene_ids: set[str],
) -> bytes:
    """Render all chapters and approved images; fail closed on mismatches."""
    if not title.strip() or not manuscript.hero_name.strip():
        raise ValueError("Title and hero are required")
    nodes = sorted(graph.nodes, key=lambda item: item.order)
    expected = {node.id for node in nodes}
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if (not expected or len(expected) != len(nodes)
            or len(chapters) != len(manuscript.chapters)
            or set(chapters) != expected):
        raise ValueError("Complete manuscript with unique scenes is required")
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in chapters.values()
    ):
        raise PermissionError("Approved manuscript is required")
    if set(illustrations) != expected or approved_scene_ids != expected:
        raise PermissionError("Every scene illustration requires explicit approval")
    # Validate all image bytes before producing any PDF pages.
    images = {scene_id: _validated_image(raw) for scene_id, raw in illustrations.items()}
    font = _font()
    output = BytesIO()
    width, height = A5
    doc = BaseDocTemplate(
        output, pagesize=A5, leftMargin=48, rightMargin=46,
        topMargin=52, bottomMargin=52, title=title,
        author="Little Legend · illustrated editorial proof",
    )
    frame = Frame(48, 52, width - 94, height - 104, showBoundary=0)

    def page(canvas, document):
        canvas.saveState()
        if document.page == 1:
            canvas.setFillColor(colors.HexColor("#F3F0FA"))
            canvas.rect(0, 0, width, height, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#D9D1F1"))
            canvas.circle(width - 40, height - 75, 95, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#E1EBF8"))
            canvas.circle(38, 65, 105, fill=1, stroke=0)
            canvas.setStrokeColor(colors.HexColor("#B8A9D9"))
            canvas.setLineWidth(1.4)
            canvas.line(52, height - 155, width - 52, height - 155)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#657089"))
        canvas.drawString(48, height - 30, "LITTLE LEGEND / EDITORIAL PROOF")
        canvas.drawCentredString(width / 2, 27, str(document.page))
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id="book", frames=[frame], onPage=page))
    title_style = ParagraphStyle(
        "Title", fontName=font, fontSize=22, leading=32,
        textColor=colors.HexColor("#293653"),
        alignment=TA_CENTER, spaceAfter=18,
    )
    heading = ParagraphStyle(
        "Chapter", fontName=font, fontSize=14, leading=22,
        textColor=colors.HexColor("#39496B"),
        alignment=TA_LEFT, spaceAfter=15, keepWithNext=True,
    )
    body = ParagraphStyle(
        "Body", fontName=font, fontSize=10, leading=17,
        textColor=colors.HexColor("#30394C"),
        spaceAfter=12, allowWidows=0, allowOrphans=0,
    )
    note = ParagraphStyle(
        "Note", parent=body, fontSize=8, leading=13,
        textColor=colors.HexColor("#657089"),
    )
    flow = [
        Spacer(1, 165),
        Paragraph(escape(title), title_style),
        Paragraph(escape(manuscript.hero_name), title_style),
        Paragraph("РЕДАКЦИОННЫЙ МАКЕТ · НЕ ДЛЯ ТИПОГРАФИИ", note),
        PageBreak(),
        Paragraph("Посвящение", title_style),
        Paragraph(escape(dedication or "Эта история — для тебя."), body),
        PageBreak(),
    ]
    for node in nodes:
        flow.append(Paragraph(
            f"Глава {node.order}. {escape(node.title)}", heading,
        ))
        flow.append(images[node.id])
        flow.append(Spacer(1, 14))
        for paragraph in chapters[node.id].text.splitlines():
            if paragraph.strip():
                flow.append(Paragraph(escape(paragraph.strip()), body))
        flow.append(PageBreak())
    flow.extend([
        Paragraph("Редакторская информация", title_style),
        Paragraph(
            "Иллюстрации и текст размещены для проверки композиции. "
            "Цветовой профиль, вылеты, переплёт и печатная подготовка "
            "не подтверждены.", note,
        ),
    ])
    doc.build(flow)
    return output.getvalue()
