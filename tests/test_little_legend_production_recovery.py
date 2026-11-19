"""Recovery planning must never repeat ambiguous paid requests."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.production_checkpoint import (
    ProductionCheckpoint,
    ProductionPhase,
)
from app.little_legend.production_recovery import (
    RecoveryAction,
    plan_recovery,
)
from app.little_legend.writer_queue import JobStatus, WriterJob


def _checkpoint(phase=ProductionPhase.MANUSCRIPT_APPROVED):
    return ProductionCheckpoint(owner_id=3, story_id=2, phase=phase, version=4)


def _job(**changes):
    params = dict(
        job_id="lli_recover_1", owner_id=3, story_id=2,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05,
    )
    params.update(changes)
    return WriterJob(**params)


def test_queued_undispatched_job_is_candidate_for_resume():
    report = plan_recovery(checkpoint=_checkpoint(), jobs=[_job()])
    assert not report.blocked
    assert report.resumable_job_ids == ["lli_recover_1"]
    assert RecoveryAction.RESUME_UNDISPATCHED_JOBS in report.actions


def test_dispatched_job_requires_reconciliation():
    report = plan_recovery(checkpoint=_checkpoint(), jobs=[
        _job(provider_dispatched_at=datetime.now(UTC)),
    ])
    assert report.blocked
    assert report.resumable_job_ids == []
    assert RecoveryAction.RECONCILE_PAID_JOB in report.actions


def test_running_job_is_never_automatically_resumed():
    report = plan_recovery(checkpoint=_checkpoint(), jobs=[
        _job(
            status=JobStatus.RUNNING, lease_token="strong-token-123456",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        ),
    ])
    assert report.blocked
    assert not report.resumable_job_ids


def test_failed_job_requires_manual_review():
    report = plan_recovery(checkpoint=_checkpoint(), jobs=[
        _job(status=JobStatus.FAILED),
    ])
    assert report.blocked
    assert RecoveryAction.REVIEW_FAILED_JOB in report.actions


def test_pending_delivery_requires_reconciliation():
    report = plan_recovery(
        checkpoint=_checkpoint(ProductionPhase.DELIVERY_PENDING), jobs=[],
    )
    assert report.blocked
    assert report.actions == [RecoveryAction.RECONCILE_DELIVERY]


def test_delivered_book_has_no_recovery_work():
    report = plan_recovery(
        checkpoint=_checkpoint(ProductionPhase.DELIVERED), jobs=[],
    )
    assert not report.blocked
    assert report.actions == [RecoveryAction.COMPLETED]


def test_foreign_job_is_rejected():
    with pytest.raises(PermissionError):
        plan_recovery(
            checkpoint=_checkpoint(), jobs=[_job(owner_id=4)],
        )


def test_duplicate_scene_jobs_are_rejected():
    with pytest.raises(ValueError, match="Duplicate scene"):
        plan_recovery(
            checkpoint=_checkpoint(),
            jobs=[_job(), _job(job_id="lli_recover_2")],
        )
