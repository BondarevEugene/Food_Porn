"""Deterministic editorial diagnostics for premium children's manuscripts.

Advisory quality signals, not proof of narrative meaning or child safety.
No provider calls, external assets, personal identifiers or billable effects.
"""
from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, Field

from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript

_WORD = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]?", re.UNICODE)


class EditorialFinding(BaseModel):
    code: str
    scene_id: str | None = None
    detail: str = Field(default="", max_length=160)


class EditorialReport(BaseModel):
    scene_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    findings: list[EditorialFinding] = Field(default_factory=list)
    requires_human_review: bool = True


def audit_manuscript(
    graph: StoryGraph,
    manuscript: StoryManuscript,
    *,
    min_chapter_words: int = 80,
    max_chapter_words: int = 1800,
    max_sentence_words: int = 42,
) -> EditorialReport:
    """Flag objectively detectable defects without inventing a quality score."""
    if not (1 <= min_chapter_words <= max_chapter_words):
        raise ValueError("Invalid chapter word limits")
    if max_sentence_words < 5:
        raise ValueError("Invalid sentence limit")
    findings: list[EditorialFinding] = []
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    ordered = sorted(graph.nodes, key=lambda node: node.order)
    word_count = 0
    normalized_texts: dict[str, str] = {}
    for node in ordered:
        chapter = chapters.get(node.id)
        if chapter is None:
            findings.append(EditorialFinding(code="chapter_missing", scene_id=node.id))
            continue
        text = chapter.text.strip()
        words = _WORD.findall(text)
        word_count += len(words)
        if len(words) < min_chapter_words:
            findings.append(EditorialFinding(
                code="chapter_too_short", scene_id=node.id,
                detail=f"{len(words)} words",
            ))
        if len(words) > max_chapter_words:
            findings.append(EditorialFinding(
                code="chapter_too_long", scene_id=node.id,
                detail=f"{len(words)} words",
            ))
        if any(len(_WORD.findall(sentence)) > max_sentence_words
               for sentence in _SENTENCE.findall(text)):
            findings.append(EditorialFinding(
                code="long_sentence", scene_id=node.id,
            ))
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if any(len(_WORD.findall(p)) > 240 for p in paragraphs):
            findings.append(EditorialFinding(
                code="dense_paragraph", scene_id=node.id,
            ))
        normalized = " ".join(text.casefold().split())
        if normalized in normalized_texts:
            findings.append(EditorialFinding(
                code="duplicate_chapter_text", scene_id=node.id,
            ))
        else:
            normalized_texts[normalized] = node.id
        if not chapter.approved:
            findings.append(EditorialFinding(
                code="chapter_not_approved", scene_id=node.id,
            ))
    unexpected = sorted(set(chapters) - {node.id for node in ordered})
    findings.extend(EditorialFinding(
        code="unexpected_chapter", scene_id=scene_id,
    ) for scene_id in unexpected)
    if not manuscript.parent_approved:
        findings.append(EditorialFinding(code="parent_approval_missing"))
    counts = Counter(f.code for f in findings)
    if len(counts) > 20:
        findings.append(EditorialFinding(code="many_distinct_findings"))
    return EditorialReport(
        scene_count=len(ordered), word_count=word_count, findings=findings,
    )
