"""Private A5 premium book assembly: distinct cover and two moments per chapter.

The renderer is provider-free; only approved, completed, revision-matched
private generated art is loaded. Never substitutes reference photos.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.little_legend.generated_art_store import (
    GeneratedArtStore,
    illustration_key,
    validate_generated_art,
)
from app.little_legend.illustrated_pdf import _editorial_paragraphs, _validated_image
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_job_context import restore_premium_job_context
from app.little_legend.premium_queue_safety import require_premium_batch_ready
from app.little_legend.print_renderer import _font
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


def validate_premium_book_jobs(
    *, owner_id: int, story_id: int, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
) -> list[IllustrationJob]:
    """Validate whole batch before a single private object read."""
    if not jobs or not all(job.premium_manifest_fingerprint for job in jobs):
        raise PermissionError("A complete premium illustration batch is required")
    if any(
        job.owner_id != owner_id or job.story_id != story_id
        or job.status != JobStatus.COMPLETED
        for job in jobs
    ):
        raise PermissionError("Premium illustrations are incomplete or cross-owner")
    first = restore_premium_job_context(jobs[0])
    manifest, plan = first.manifest, first.plan
    story_fingerprint = require_premium_batch_ready(
        manifest=manifest, plan=plan, graph=graph, manuscript=manuscript,
        owner_id=owner_id, story_id=story_id,
    )
    expected = [request.moment_id for request in manifest.requests]
    if len(jobs) != len(expected) or {job.scene_id for job in jobs} != set(expected):
        raise PermissionError("Cover and both moments of every chapter are required")
    if len({job.job_id for job in jobs}) != len(jobs):
        raise PermissionError("Duplicate premium job identifiers")
    by_moment = {job.scene_id: job for job in jobs}
    for job in jobs:
        context = restore_premium_job_context(job)
        if (
            context.manifest.fingerprint != manifest.fingerprint
            or context.plan != plan
            or job.premium_story_fingerprint != story_fingerprint
        ):
            raise PermissionError("Premium batch mixes different production plans")
    return [by_moment[moment_id] for moment_id in expected]


def assemble_premium_book_pdf(
    *, store: GeneratedArtStore, owner_id: int, story_id: int,
    title: str, dedication: str, graph: StoryGraph,
    manuscript: StoryManuscript, jobs: list[IllustrationJob],
) -> bytes:
    """Render a complete premium editorial proof without billable AI calls."""
    ordered = validate_premium_book_jobs(
        owner_id=owner_id, story_id=story_id, graph=graph,
        manuscript=manuscript, jobs=jobs,
    )
    if not title.strip():
        raise ValueError("Book title is required")
    art = {}
    for job in ordered:
        raw = store.get(key=illustration_key(
            owner_id=owner_id, story_id=story_id, job_id=job.job_id,
        ))
        validate_generated_art(raw)
        art[job.scene_id] = _validated_image(raw)
    font = _font()
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A5, leftMargin=45, rightMargin=45,
        topMargin=44, bottomMargin=44, title=title,
        author="Little Legend",
    )
    heading = ParagraphStyle(
        "PremiumHeading", fontName=font, fontSize=20, leading=29,
        alignment=TA_CENTER, textColor=colors.HexColor("#2A3152"),
        spaceAfter=18,
    )
    chapter_style = ParagraphStyle(
        "PremiumChapter", parent=heading, fontSize=16, leading=23,
        alignment=TA_LEFT,
    )
    body = ParagraphStyle(
        "PremiumBody", fontName=font, fontSize=10.5, leading=17,
        textColor=colors.HexColor("#2A3152"), spaceAfter=10,
        splitLongWords=1,
    )
    nodes = sorted(graph.nodes, key=lambda item: item.order)
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    flow = [
        Paragraph(escape(title), heading),
        Spacer(1, 12), art["premium-cover"],
        Spacer(1, 14), Paragraph(escape(manuscript.hero_name), body),
        PageBreak(), Paragraph("Посвящение", heading),
        Paragraph(escape(dedication or "Эта история — для тебя."), body),
        PageBreak(),
    ]
    for node in nodes:
        flow.extend([
            Paragraph(escape(f"Глава {node.order}. {node.title}"), chapter_style),
            art[f"chapter-{node.order:02d}-moment-1"],
            Spacer(1, 12),
        ])
        for paragraph in _editorial_paragraphs(chapters[node.id].text):
            flow.append(Paragraph(escape(paragraph), body))
        flow.extend([
            PageBreak(),
            Paragraph(escape(f"Глава {node.order}. Продолжение"), chapter_style),
            art[f"chapter-{node.order:02d}-moment-2"],
            PageBreak(),
        ])
    doc.build(flow)
    pdf = output.getvalue()
    if not pdf.startswith(b"%PDF-") or len(pdf) < 1024:
        raise ValueError("Premium PDF rendering failed")
    return pdf
