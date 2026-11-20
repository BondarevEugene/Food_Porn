"""Stable, privacy-safe release statuses for customer and operator interfaces."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.little_legend.release_quality_engine import ReleaseAudit

ReleaseStatus = Literal["ready", "needs_correction", "blocked"]

BLOCKING_ISSUES = frozenset({
    "paid_delivery_gate_failed",
    "pdf_content_unreadable",
    "editorial_proof_not_deliverable",
    "illustrations_missing",
    "chapter_art_missing",
    "insufficient_pages",
})


class ReleaseDecision(BaseModel):
    status: ReleaseStatus
    can_deliver: bool
    retry_allowed: bool
    issue_codes: list[str] = Field(default_factory=list)


def decide_release(audit: ReleaseAudit) -> ReleaseDecision:
    """Map a deterministic audit to UI status; never trigger payments or jobs."""
    if audit.deliverable:
        return ReleaseDecision(
            status="ready", can_deliver=True, retry_allowed=False,
            issue_codes=list(audit.issue_codes),
        )
    blocked = audit.edition != "digital" or bool(
        BLOCKING_ISSUES.intersection(audit.issue_codes)
    )
    return ReleaseDecision(
        status="blocked" if blocked else "needs_correction",
        can_deliver=False,
        retry_allowed=not blocked,
        issue_codes=list(audit.issue_codes),
    )
