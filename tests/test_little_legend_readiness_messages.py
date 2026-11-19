"""Customer-facing readiness messages never disclose private story content."""
from app.little_legend.production_readiness import (
    ProductionReadiness,
    ProductionStage,
    ReadinessIssue,
)
from app.little_legend.readiness_messages import readiness_message


def report(*codes: str, ready: bool = False) -> ProductionReadiness:
    return ProductionReadiness(
        ready_for_export=ready,
        ready_for_delivery=False,
        completed_scenes=0,
        total_scenes=12,
        issues=[
            ReadinessIssue(
                code=code, stage=ProductionStage.ILLUSTRATIONS,
                scene_id="private-scene-id",
            )
            for code in codes
        ],
    )


def test_readiness_explains_blockers_without_scene_ids() -> None:
    result = readiness_message(
        report("illustration_incomplete", "illustration_incomplete"),
        language="ru",
    )
    assert "Дождитесь иллюстраций" in result
    assert result.count("Дождитесь иллюстраций") == 1
    assert "private-scene-id" not in result


def test_readiness_reports_approved_book() -> None:
    assert "ready for assembly" in readiness_message(
        report(ready=True), language="en",
    )


def test_readiness_ignores_pdf_not_verified_for_preparation() -> None:
    result = readiness_message(report("pdf_not_verified"), language="en")
    assert "pdf_not_verified" not in result
    assert "PDF" not in result


def test_readiness_unknown_codes_do_not_leak_raw_payload() -> None:
    result = readiness_message(report("secret-child-name"), language="en")
    assert "Review required" in result
    assert "secret-child-name" not in result
