"""Release decisions preserve paid-delivery safety and retry semantics."""

from app.little_legend.release_decision import decide_release
from app.little_legend.release_quality_engine import ReleaseAudit


def _audit(*, deliverable: bool, issues: list[str], edition: str = "digital"):
    return ReleaseAudit(
        edition=edition, deliverable=deliverable, page_count=3,
        expected_scenes=1, illustration_count=1, issue_codes=issues,
    )


def test_deliverable_book_is_ready_without_another_payment():
    result = decide_release(_audit(
        deliverable=True, issues=["low_resolution_illustrations"],
    ))
    assert result.status == "ready"
    assert result.can_deliver
    assert not result.retry_allowed


def test_missing_chapter_art_blocks_delivery():
    result = decide_release(_audit(
        deliverable=False, issues=["chapter_art_missing"],
    ))
    assert result.status == "blocked"
    assert not result.can_deliver


def test_correctable_layout_defect_can_be_rechecked_without_payment():
    result = decide_release(_audit(
        deliverable=False, issues=["layout_review_required"],
    ))
    assert result.status == "needs_correction"
    assert result.retry_allowed
    assert not result.can_deliver


def test_editorial_proof_never_becomes_paid_delivery():
    result = decide_release(_audit(
        deliverable=False, issues=["editorial_proof_not_deliverable"],
        edition="editorial_proof",
    ))
    assert result.status == "blocked"
    assert not result.can_deliver
