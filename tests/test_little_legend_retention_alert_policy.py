"""Deterministic aggregate-only monitoring policy."""
import pytest

from app.little_legend.retention_alert_policy import evaluate_retention


def audit(*, expired=0, exhausted=0, pending=0):
    return {
        "expired_not_deleted": expired,
        "exhausted_retries": exhausted,
        "pending_over_24h": pending,
        "launch_blockers": ["photo_upload_not_implemented"],
    }


def test_healthy_without_photo_upload():
    result = evaluate_retention(audit())
    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.codes == ()


def test_expired_backlog_is_warning():
    result = evaluate_retention(audit(expired=3, pending=2))
    assert result.status == "warning"
    assert result.exit_code == 2
    assert result.codes == (
        "RETENTION_EXPIRED_BACKLOG",
        "RETENTION_PENDING_OVER_24H",
    )


def test_exhausted_retries_are_critical():
    result = evaluate_retention(audit(exhausted=1))
    assert result.status == "critical"
    assert result.exit_code == 3


def test_failed_physical_delete_is_critical():
    result = evaluate_retention(
        audit(), retention={"deletion_failed": 1},
    )
    assert result.exit_code == 3
    assert result.codes == ("RETENTION_DELETE_FAILED",)


def test_thresholds_are_configurable():
    result = evaluate_retention(
        audit(expired=2, pending=3),
        max_expired=2, max_pending_24h=3,
    )
    assert result.exit_code == 0


@pytest.mark.parametrize("value", [-1, True, "1", None])
def test_rejects_invalid_counts(value):
    with pytest.raises(ValueError):
        evaluate_retention({**audit(), "expired_not_deleted": value})


def test_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        evaluate_retention(audit(), max_expired=-1)
