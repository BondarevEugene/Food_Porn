"""Privacy-preserving retention operational policy and alert thresholds.

All decisions use aggregate counts only, never child identifiers or object keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RetentionDecision:
    status: str
    codes: tuple[str, ...]
    exit_code: int
    metrics: dict[str, int]


def evaluate_retention(
    audit: Mapping[str, Any], *,
    retention: Mapping[str, Any] | None = None,
    max_expired: int = 0,
    max_pending_24h: int = 0,
) -> RetentionDecision:
    """Return a deterministic, monitoring-ready operational decision.

    Exit codes: 0 healthy; 2 actionable backlog; 3 physical deletion failure.
    Launch blockers are deliberately not treated as a runtime failure because
    photo upload must remain disabled until separately approved.
    """
    if max_expired < 0 or max_pending_24h < 0:
        raise ValueError("Alert thresholds must be nonnegative")
    keys = ("expired_not_deleted", "exhausted_retries", "pending_over_24h")
    metrics: dict[str, int] = {}
    for key in keys:
        value = audit[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Invalid retention audit metric")
        metrics[key] = value
    failed = 0
    if retention is not None:
        failed = retention["deletion_failed"]
        if isinstance(failed, bool) or not isinstance(failed, int) or failed < 0:
            raise ValueError("Invalid deletion failure count")
    metrics["deletion_failed"] = failed
    codes = []
    if metrics["expired_not_deleted"] > max_expired:
        codes.append("RETENTION_EXPIRED_BACKLOG")
    if metrics["pending_over_24h"] > max_pending_24h:
        codes.append("RETENTION_PENDING_OVER_24H")
    if metrics["exhausted_retries"]:
        codes.append("RETENTION_RETRY_EXHAUSTED")
    if failed:
        codes.append("RETENTION_DELETE_FAILED")
    severity = 3 if failed or metrics["exhausted_retries"] else 2 if codes else 0
    return RetentionDecision(
        status="critical" if severity == 3 else "warning" if severity else "ok",
        codes=tuple(codes),
        exit_code=severity,
        metrics=metrics,
    )
