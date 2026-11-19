"""In-memory illustration assembly for an approved Little Legend manuscript.

The caller must independently verify owner, provider consent and budget before
calling this function. No files, URLs or photos are stored or transferred here.
"""
from __future__ import annotations

from typing import Protocol

from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.image_ai_consent import (
    ImageAIConsent,
    ImageAIDisclosure,
    consent_allows_image_ai,
)
from app.little_legend.story_graph import SceneNode, StoryGraph
from app.little_legend.story_writer import StoryManuscript


class SceneIllustrator(Protocol):
    async def generate_scene(
        self, *, scene: SceneNode, hero: str, style: str,
        continuity: str = "",
    ) -> bytes: ...


async def produce_illustrated_book(
    *, illustrator: SceneIllustrator, title: str, dedication: str,
    graph: StoryGraph, manuscript: StoryManuscript, style: str,
    approved_scene_ids: set[str], continuity: str = "",
    image_ai_consent: ImageAIConsent | None = None,
    image_ai_disclosure: ImageAIDisclosure | None = None,
) -> bytes:
    """Generate every explicitly approved scene and render an A5 editorial PDF.

    All approval and completeness checks happen *before* the first paid call.
    A failure produces no partial book; retry and persistence belong to caller.
    """
    if (image_ai_consent is None or image_ai_disclosure is None
            or not consent_allows_image_ai(image_ai_consent, image_ai_disclosure)):
        raise PermissionError("Explicit image AI consent is required")
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    expected = {node.id for node in nodes}
    if (not expected or len(expected) != len(nodes)
            or approved_scene_ids != expected):
        raise PermissionError("All scene illustrations require explicit approval")
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in manuscript.chapters
    ):
        raise PermissionError("Complete manuscript approval is required")
    if (len(manuscript.chapters) != len(expected)
            or {chapter.scene_id for chapter in manuscript.chapters} != expected):
        raise ValueError("Manuscript does not match story scenes")
    if not title.strip() or not style.strip() or not manuscript.hero_name.strip():
        raise ValueError("Book title and style are required")
    images = {}
    for node in nodes:
        images[node.id] = await illustrator.generate_scene(
            scene=node, hero=manuscript.hero_name, style=style,
            continuity=continuity,
        )
    return render_illustrated_proof(
        title=title, dedication=dedication, graph=graph,
        manuscript=manuscript, illustrations=images,
        approved_scene_ids=approved_scene_ids,
    )
