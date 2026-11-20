"""Privacy-safe deterministic manuscript diagnostics, not semantic certification."""
from __future__ import annotations

import re
from collections import Counter

from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript

_WORD = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)
_SENTENCE = re.compile(r"[.!?…]+")


def manuscript_quality_report(
    graph: StoryGraph, manuscript: StoryManuscript | None,
) -> dict[str, object]:
    """Return only scene counts and issue codes, never private prose."""
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    chapters = {chapter.scene_id: chapter for chapter in (
        manuscript.chapters if manuscript else []
    )}
    scenes: list[dict[str, object]] = []
    issues: Counter[str] = Counter()
    openings: set[str] = set()
    for node in nodes:
        chapter = chapters.get(node.id)
        prose = chapter.text.strip() if chapter else ""
        words = _WORD.findall(prose)
        count = len(words)
        sentences = len(_SENTENCE.findall(prose))
        paragraphs = sum(bool(part.strip()) for part in prose.splitlines())
        codes: list[str] = []
        if chapter is None:
            codes.append("CHAPTER_MISSING")
        else:
            if count < 45:
                codes.append("CHAPTER_TOO_SHORT")
            if count > 1500:
                codes.append("CHAPTER_TOO_LONG")
            if sentences < 3:
                codes.append("SENTENCE_VARIETY_REVIEW")
            if paragraphs < 2:
                codes.append("PARAGRAPH_STRUCTURE_REVIEW")
            if not chapter.approved:
                codes.append("CHAPTER_NOT_APPROVED")
            opening = " ".join(word.casefold() for word in words[:8])
            if opening and opening in openings:
                codes.append("REPEATED_CHAPTER_OPENING")
            if opening:
                openings.add(opening)
        issues.update(codes)
        scenes.append({
            "scene_id": node.id,
            "order": node.order,
            "word_count": count,
            "sentence_count": sentences,
            "paragraph_count": paragraphs,
            "approved": bool(chapter and chapter.approved),
            "codes": codes,
        })
    if manuscript is None or not manuscript.parent_approved:
        issues["PARENT_APPROVAL_REQUIRED"] += 1
    if manuscript is not None:
        unknown = set(chapters) - {node.id for node in nodes}
        if unknown:
            issues["UNEXPECTED_CHAPTER"] += len(unknown)
    hard = {
        "CHAPTER_MISSING", "CHAPTER_TOO_SHORT", "CHAPTER_TOO_LONG",
        "CHAPTER_NOT_APPROVED", "PARENT_APPROVAL_REQUIRED",
        "UNEXPECTED_CHAPTER",
    }
    return {
        "version": "manuscript-quality-v1",
        "scene_count": len(nodes),
        "completed_scenes": sum(scene["word_count"] > 0 for scene in scenes),
        "total_words": sum(scene["word_count"] for scene in scenes),
        "scenes": scenes,
        "issue_counts": dict(sorted(issues.items())),
        "ready_for_editorial_human_review": not bool(hard & issues.keys()),
        "ready_for_publication": False,
        "semantic_quality_verified": False,
        "photo_processing_enabled": False,
    }
