"""Premium A5 book renderer: distinct cover and two full-page scenes per chapter.

This renderer never calls AI or loads customer media from remote storage.
Only explicitly approved, validated bytes may enter the PDF. Physical leather,
embossing and ribbons are represented as printable visual motifs, not claimed
as physical print finishes.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
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

from app.little_legend.illustrated_pdf import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    _editorial_paragraphs,
)
from app.little_legend.premium_visual_contract import BookVisualPlan
from app.little_legend.print_renderer import _font
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


def _validate_art(raw: bytes) -> tuple[int, int]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Missing or oversized illustration")
    try:
        with PILImage.open(BytesIO(raw)) as im:
            if im.format not in {"JPEG", "PNG"}:
                raise ValueError("Only JPEG and PNG illustrations are supported")
            width, height = im.size
            if min(width, height) < 300 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Unsupported illustration dimensions")
            im.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Invalid illustration bytes") from exc
    return width, height


def render_premium_book(
    *,
    title: str,
    dedication: str,
    graph: StoryGraph,
    manuscript: StoryManuscript,
    plan: BookVisualPlan,
    cover: bytes,
    illustrations: dict[str, bytes],
    approved_moment_ids: set[str],
    cover_approved: bool,
) -> bytes:
    """Fail closed unless all chapter moments and the cover are approved.

    The producer must independently verify identity consistency, likeness,
    narrative relevance and face-safe margins before setting approval flags.
    """
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    chapter_by_id = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if not title.strip() or not manuscript.hero_name.strip():
        raise ValueError("Book title and hero are required")
    if not nodes or len(nodes) != len(plan.illustrations) // 2:
        raise ValueError("Visual plan must contain two moments per chapter")
    if len(chapter_by_id) != len(manuscript.chapters) or (
        set(chapter_by_id) != {node.id for node in nodes}
    ):
        raise ValueError("Every chapter must have unique matching scene")
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in chapter_by_id.values()
    ):
        raise PermissionError("Complete approved manuscript is required")
    expected = {slot.moment_id for slot in plan.illustrations}
    if set(illustrations) != expected or approved_moment_ids != expected:
        raise PermissionError("Every unique illustration must be approved")
    if not cover_approved:
        raise PermissionError("Separate personalized cover approval is required")
    sizes = {key: _validate_art(raw) for key, raw in illustrations.items()}
    cover_size = _validate_art(cover)

    width, height = A5
    design = plan.design
    paper = colors.HexColor(design.paper_tone)
    ink = colors.HexColor(design.ink_color)
    gold = colors.HexColor("#B78B3F")
    font = _font()
    output = BytesIO()
    doc = BaseDocTemplate(
        output, pagesize=A5, leftMargin=43, rightMargin=43,
        topMargin=49, bottomMargin=49, title=title,
        author="Little Legend · premium personalized story",
    )
    frame = Frame(43, 49, width - 86, height - 98, showBoundary=0)

    def draw_background(canvas, document):
        canvas.saveState()
        canvas.setFillColor(paper)
        canvas.rect(0, 0, width, height, stroke=0, fill=1)
        # Restrained genre ornaments: no texture behind text.
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(0.65)
        canvas.roundRect(18, 18, width - 36, height - 36, 5, fill=0, stroke=1)
        canvas.setStrokeColor(ink)
        canvas.setLineWidth(0.3)
        canvas.line(31, height - 36, width - 31, height - 36)
        canvas.setFont(font, 7.5)
        canvas.setFillColor(ink)
        canvas.drawCentredString(width / 2, 27, f"Little Legend  ·  {document.page}")
        canvas.restoreState()

    doc.addPageTemplates(PageTemplate(id="premium", frames=[frame], onPage=draw_background))
    title_style = ParagraphStyle(
        "PremiumTitle", fontName=font, fontSize=19, leading=26,
        textColor=ink, alignment=TA_CENTER, spaceAfter=18,
    )
    chapter_style = ParagraphStyle(
        "PremiumChapter", parent=title_style, fontSize=15, leading=22,
    )
    body_style = ParagraphStyle(
        "PremiumBody", fontName=font, fontSize=10.5, leading=17.5,
        textColor=ink, alignment=TA_JUSTIFY, spaceAfter=12,
        firstLineIndent=12, allowWidows=0, allowOrphans=0,
    )
    caption_style = ParagraphStyle(
        "PremiumCaption", parent=body_style, fontSize=8.5,
        leading=13, alignment=TA_CENTER, firstLineIndent=0,
    )

    def full_page_art(raw: bytes, size: tuple[int, int], caption: str):
        # Full-width image, aspect-ratio preserved; no crop or stretch.
        available_w, available_h = width - 92, height - 170
        scale = min(available_w / size[0], available_h / size[1])
        from reportlab.platypus import Image as FlowImage

        return [
            Spacer(1, 8),
            FlowImage(BytesIO(raw), width=size[0] * scale, height=size[1] * scale),
            Spacer(1, 13),
            Paragraph(escape(caption), caption_style),
            PageBreak(),
        ]

    flow = [
        Spacer(1, 10),
        Paragraph(escape(title), title_style),
        Paragraph(escape(manuscript.hero_name), chapter_style),
        Spacer(1, 5),
    ]
    flow.extend(full_page_art(cover, cover_size, "Персональная история"))
    flow.extend([
        Paragraph("Посвящение", title_style),
        Paragraph(escape(dedication or "Эта история — для тебя."), body_style),
        PageBreak(),
    ])
    for index, node in enumerate(nodes):
        chapter = chapter_by_id[node.id]
        flow.extend([
            Paragraph(f"Глава {node.order:02d}", caption_style),
            Paragraph(escape(node.title), chapter_style),
            PageBreak(),
        ])
        slots = plan.illustrations[index * 2:index * 2 + 2]
        # Two separate illustrated leaves; text follows without dropping prose.
        for slot in slots:
            flow.extend(full_page_art(
                illustrations[slot.moment_id], sizes[slot.moment_id],
                slot.scene_description,
            ))
        for paragraph in _editorial_paragraphs(chapter.text):
            flow.append(Paragraph(escape(paragraph), body_style))
        flow.append(PageBreak())
    if isinstance(flow[-1], PageBreak):
        flow.pop()
    doc.build(flow)
    return output.getvalue()
