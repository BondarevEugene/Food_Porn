"""Owner-scoped recovery metrics never leak other customers' books."""
import pytest

from app.little_legend.production_recovery import (
    RecoveryAction,
    RecoveryPlan,
)
from app.little_legend.production_recovery_dashboard import summarize_recovery


def _plan(story_id, **overrides):
    data = dict(
        owner_id=3, story_id=story_id, checkpoint_version=2,
        actions=[RecoveryAction.INSPECT_ILLUSTRATIONS],
    )
    data.update(overrides)
    return RecoveryPlan(**data)


def test_dashboard_counts_blocked_and_actionable_books():
    dashboard = summarize_recovery(owner_id=3, plans=[
        _plan(
            1, actions=[RecoveryAction.RESUME_UNDISPATCHED_JOBS],
            resumable_job_ids=["lli_recover_1"],
        ),
        _plan(
            2, actions=[RecoveryAction.RECONCILE_PAID_JOB],
            blocked=True,
        ),
    ])
    assert dashboard.total_unfinished == 2
    assert dashboard.blocked == 1
    assert dashboard.actionable == 1
    assert dashboard.action_counts["reconcile_paid_job"] == 1


def test_dashboard_rejects_foreign_owner():
    with pytest.raises(PermissionError):
        summarize_recovery(owner_id=4, plans=[_plan(1)])


def test_dashboard_rejects_duplicate_stories():
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_recovery(owner_id=3, plans=[_plan(1), _plan(1)])
