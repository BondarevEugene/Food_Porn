"""Deterministic, provider-independent Little Legend job state machine.

The state machine is serializable for durable storage; no network calls occur.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPolicy(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    lease_seconds: int = Field(default=180, ge=30, le=3600)
    retry_base_seconds: int = Field(default=15, ge=1, le=3600)
    max_estimated_cost_usd: float = Field(default=0.25, gt=0, le=20)


class WriterJob(BaseModel):
    job_id: str = Field(min_length=8, max_length=120)
    story_id: int = Field(gt=0)
    owner_id: int = Field(gt=0)
    scene_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    status: JobStatus = JobStatus.QUEUED
    attempt: int = Field(default=0, ge=0)
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    retry_after: datetime | None = None
    error_code: str | None = None
    provider_dispatched_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lease(self) -> WriterJob:
        if self.status == JobStatus.RUNNING and (
            not self.lease_token or self.lease_expires_at is None
        ):
            raise ValueError("Running jobs require a lease")
        return self


def claim_job(
    job: WriterJob, *, token: str, policy: JobPolicy,
    now: datetime | None = None,
) -> WriterJob:
    """Caller must compare-and-swap the serialized job in durable storage."""
    now = now or datetime.now(UTC)
    if not token or len(token) < 16:
        raise ValueError("Strong unique lease token required")
    if job.provider_dispatched_at is not None:
        raise PermissionError("Provider dispatch requires manual reconciliation")
    if job.estimated_cost_usd > policy.max_estimated_cost_usd:
        raise PermissionError("Job exceeds estimated cost ceiling")
    claimable = job.status == JobStatus.QUEUED or (
        job.status == JobStatus.RETRY_WAIT
        and job.retry_after is not None and job.retry_after <= now
    ) or (
        job.status == JobStatus.RUNNING
        and job.lease_expires_at is not None and job.lease_expires_at <= now
    )
    if not claimable:
        raise ValueError("Job is not claimable")
    if job.attempt >= policy.max_attempts:
        raise ValueError("Retry budget exhausted")
    return job.model_copy(update={
        "status": JobStatus.RUNNING,
        "attempt": job.attempt + 1,
        "lease_token": token,
        "lease_expires_at": now + timedelta(seconds=policy.lease_seconds),
        "retry_after": None,
        "error_code": None,
    })


def finish_job(
    job: WriterJob, *, token: str, success: bool, policy: JobPolicy,
    error_code: str = "provider_error", retryable: bool = True,
    now: datetime | None = None,
) -> WriterJob:
    now = now or datetime.now(UTC)
    if job.status != JobStatus.RUNNING or job.lease_token != token:
        raise PermissionError("Worker no longer owns this job")
    if job.lease_expires_at is None or job.lease_expires_at <= now:
        raise PermissionError("Worker lease expired")
    if success:
        status = JobStatus.COMPLETED
        retry_after = None
    elif retryable and job.attempt < policy.max_attempts:
        status = JobStatus.RETRY_WAIT
        retry_after = now + timedelta(
            seconds=min(policy.retry_base_seconds * 2 ** (job.attempt - 1), 3600)
        )
    else:
        status = JobStatus.FAILED
        retry_after = None
    return job.model_copy(update={
        "status": status,
        "lease_token": None,
        "lease_expires_at": None,
        "retry_after": retry_after,
        "error_code": None if success else error_code[:100],
    })


def cancel_job(job: WriterJob) -> WriterJob:
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
        raise ValueError("Terminal job cannot be cancelled")
    return job.model_copy(update={
        "status": JobStatus.CANCELLED,
        "lease_token": None,
        "lease_expires_at": None,
        "retry_after": None,
    })
