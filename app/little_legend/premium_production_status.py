"""Safe customer-facing status for a premium illustration batch.

No lease tokens, private references, provider prompts or error strings escape.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.writer_queue import JobStatus


def premium_production_status(
    jobs: list[IllustrationJob], *, now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    premium = [job for job in jobs if job.premium_manifest_fingerprint]
    counts = Counter(job.status.value for job in premium)
    if not premium:
        state, message = "not_started", "Генерация иллюстраций ещё не запущена"
    elif len(premium) != len(jobs):
        state, message = "blocked", "Обнаружено смешение партий иллюстраций"
    elif any(job.status == JobStatus.FAILED for job in premium):
        state, message = "attention_required", "Генерация требует проверки оператором"
    elif any(
        job.provider_dispatched_at is not None
        and job.status == JobStatus.RUNNING
        and job.lease_expires_at is not None
        and job.lease_expires_at <= now
        for job in premium
    ):
        state, message = "reconciliation", "Проверяем результат генерации"
    elif all(job.status == JobStatus.COMPLETED for job in premium):
        state, message = "illustrations_complete", "Иллюстрации готовы"
    elif any(job.status == JobStatus.CANCELLED for job in premium):
        state, message = "blocked", "Генерация остановлена"
    elif any(job.status == JobStatus.RUNNING for job in premium):
        state, message = "generating", "Создаём иллюстрации"
    elif any(job.status == JobStatus.RETRY_WAIT for job in premium):
        state, message = "retry_scheduled", "Ожидаем безопасного повторного запуска"
    else:
        state, message = "queued", "Иллюстрации ожидают обработки"
    return {
        "state": state,
        "message": message,
        "completed": counts[JobStatus.COMPLETED.value],
        "total": len(premium),
        "requires_attention": state in {"attention_required", "reconciliation", "blocked"},
    }
