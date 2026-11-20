"""Release operations never expose customer text or perform paid work."""

import pytest

from app.little_legend.release_operations import present_release_audit
from app.little_legend.release_quality_engine import ReleaseAudit


def _audit(*, deliverable=True, edition="digital", issues=None):
    return ReleaseAudit(
        edition=edition, deliverable=deliverable,
        page_count=14, expected_scenes=12, illustration_count=12,
        issue_codes=issues or [],
    )


def test_ready_book_has_operator_summary_without_private_content():
    report = present_release_audit(_audit())
    assert report.status == "ready"
    assert report.can_deliver
    assert not report.print_ready
    assert report.page_count == 14
    assert "manuscript" not in report.model_dump()
    assert "pdf" not in report.model_dump()


@pytest.mark.parametrize("code", [
    "paid_delivery_gate_failed",
    "chapter_art_missing",
    "illustrations_missing",
    "insufficient_pages",
    "pdf_content_unreadable",
])
def test_blocking_issues_have_actionable_messages(code):
    report = present_release_audit(_audit(
        deliverable=False, issues=[code],
    ))
    assert report.status == "blocked"
    assert not report.can_deliver
    assert report.issues[0].title
    assert report.issues[0].action


def test_dpi_warning_does_not_block_digital_delivery():
    report = present_release_audit(_audit(
        issues=["low_resolution_illustrations"],
    ))
    assert report.status == "ready"
    assert report.can_deliver
    assert report.issues[0].severity == "warning"


def test_editorial_proof_never_can_be_delivered():
    report = present_release_audit(_audit(
        deliverable=False, edition="editorial_proof",
        issues=["editorial_proof_not_deliverable"],
    ))
    assert report.status == "blocked"
    assert not report.can_deliver


def test_unknown_issue_does_not_leak_private_data():
    report = present_release_audit(_audit(
        deliverable=False, issues=["unrecognized_issue"],
    ))
    assert report.issues[0].title == "Неизвестная проблема"
    assert report.issues[0].code == "unrecognized_issue"


def test_correctable_issue_can_be_rechecked_without_payment():
    report = present_release_audit(_audit(
        deliverable=False, issues=["layout_review_required"],
    ))
    assert report.status == "needs_correction"
    assert report.can_recheck_without_payment
    assert not report.can_deliver


def test_duplicate_codes_are_collapsed_in_operator_view():
    report = present_release_audit(_audit(
        deliverable=False,
        issues=["chapter_art_missing", "chapter_art_missing"],
    ))
    assert len(report.issues) == 1
