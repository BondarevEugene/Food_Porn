"""Deterministic manuscript diagnostics, never an automatic literary approval."""
from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, Field

from app.little_legend.story_writer import StoryManuscript

_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]?", re.UNICODE)


class EditorialFinding(BaseModel):
    code: str
    scene_id: str
    detail: str
    severity: str = "review"


class ManuscriptDiagnostics(BaseModel):
    chapter_count: int = Field(ge=0)
    total_words: int = Field(ge=0)
    findings: list[EditorialFinding] = Field(default_factory=list)
    human_review_required: bool = True
    literary_quality_verified: bool = False


def _normalized_sentences(text: str) -> list[str]:
    normalized = []
    for match in _SENTENCE.finditer(text):
        sentence = " ".join(match.group().casefold().split()).strip(" .!?…")
        if len(_WORD.findall(sentence)) >= 6:
            normalized.append(sentence)
    return normalized


def diagnose_manuscript(
    manuscript: StoryManuscript, *, minimum_words: int = 80,
    maximum_words: int = 3000,
) -> ManuscriptDiagnostics:
    """Flag measurable editorial risks without reading personal metadata."""
    if not 1 <= minimum_words <= maximum_words <= 20000:
        raise ValueError("Invalid editorial word limits")
    findings: list[EditorialFinding] = []
    seen: dict[str, str] = {}
    total_words = 0
    for chapter in manuscript.chapters:
        words = _WORD.findall(chapter.text)
        count = len(words)
        total_words += count
        if count < minimum_words:
            findings.append(EditorialFinding(
                code="chapter_too_short", scene_id=chapter.scene_id,
                detail=f"{count} words; minimum {minimum_words}",
            ))
        if count > maximum_words:
            findings.append(EditorialFinding(
                code="chapter_too_long", scene_id=chapter.scene_id,
                detail=f"{count} words; maximum {maximum_words}",
            ))
        sentences = _normalized_sentences(chapter.text)
        repeated = Counter(sentences)
        if any(amount >= 3 for amount in repeated.values()):
            findings.append(EditorialFinding(
                code="repeated_sentence", scene_id=chapter.scene_id,
                detail="A substantial sentence appears at least three times",
            ))
        for sentence in set(sentences):
            previous = seen.get(sentence)
            if previous is not None and previous != chapter.scene_id:
                findings.append(EditorialFinding(
                    code="cross_chapter_repetition", scene_id=chapter.scene_id,
                    detail=f"A substantial sentence also appears in {previous}",
                ))
                break
        for sentence in sentences:
            seen.setdefault(sentence, chapter.scene_id)
    return ManuscriptDiagnostics(
        chapter_count=len(manuscript.chapters),
        total_words=total_words,
        findings=findings,
    )
