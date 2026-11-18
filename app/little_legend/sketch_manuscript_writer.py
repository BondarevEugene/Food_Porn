"""Write a manuscript from an approved parent sketch, one chapter at a time.

A trusted caller supplies the provider and persistence callback. No provider is
created and no external data is sent until the caller explicitly invokes this.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.client_sketch import ParentSketch
from app.little_legend.hero_contract import HeroContract
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.sketch_writer_briefs import (
    SketchWritingSettings,
    compose_sketch_chapter_briefs,
)
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import (
    MAX_CHAPTER_CHARACTERS,
    ChapterDraft,
    StoryManuscript,
    WriterProvider,
    WritingPolicy,
)


async def write_sketch_manuscript(
    *, provider: WriterProvider, sketch: ParentSketch, graph: StoryGraph,
    contract: HeroContract, blueprint: BookBlueprint, design: StoryDesign,
    settings: SketchWritingSettings, policy: WritingPolicy,
    outline_approved: bool, external_processing_authorized: bool,
    existing: StoryManuscript | None = None,
    on_chapter: Callable[[ChapterDraft], Awaitable[None]] | None = None,
) -> StoryManuscript:
    """Generate chapters sequentially with evolving manuscript continuity.

    Never use this directly as a public endpoint. Production execution must
    supply a trusted, lease-fenced persistence callback.
    """
    if not policy.enabled:
        raise PermissionError("AI writing is disabled")
    if not external_processing_authorized:
        raise PermissionError("External AI processing requires explicit authorization")
    current = existing.model_copy(deep=True) if existing else StoryManuscript(
        hero_name=contract.hero_name,
    )
    initial = compose_sketch_chapter_briefs(
        sketch=sketch, graph=graph, contract=contract, blueprint=blueprint,
        design=design, settings=settings, outline_approved=outline_approved,
        existing=current,
    )
    if len(initial) > policy.max_chapters_per_request:
        raise ValueError("Too many chapters requested")
    for target in initial:
        # Rebuild context after each chapter so subsequent chapters receive
        # freshly written prose rather than a stale initial snapshot.
        fresh = compose_sketch_chapter_briefs(
            sketch=sketch, graph=graph, contract=contract, blueprint=blueprint,
            design=design, settings=settings, outline_approved=outline_approved,
            existing=current,
        )
        brief = next(
            item for item in fresh if item["scene_id"] == target["scene_id"]
        )
        text = await provider.write_chapter(brief)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("AI writer returned an empty chapter")
        if len(text) > MAX_CHAPTER_CHARACTERS:
            raise ValueError("AI writer returned an oversized chapter")
        previous = next(
            (chapter for chapter in current.chapters
             if chapter.scene_id == target["scene_id"]), None,
        )
        chapter = ChapterDraft(
            scene_id=target["scene_id"], text=text.strip(),
            revision=previous.revision + 1 if previous else 1,
        )
        if on_chapter is not None:
            await on_chapter(chapter)
        current.chapters = [
            item for item in current.chapters
            if item.scene_id != chapter.scene_id
        ] + [chapter]
        current.parent_approved = False
    order = {
        node.id: node.order for node in graph.nodes
    }
    current.chapters.sort(key=lambda item: order[item.scene_id])
    return current
