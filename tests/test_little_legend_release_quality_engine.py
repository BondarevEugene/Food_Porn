"""Release audit regression tests against the existing book renderer."""
from io import BytesIO

import pytest
from PIL import Image as PILImage

from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.release_quality_engine import audit_book_release
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _sample(edition: str) -> tuple[bytes, dict[str, bytes]]:
    graph = build_graph(["Сад чудес"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        parent_approved=True,
        chapters=[
            ChapterDraft(
                scene_id="scene_1",
                text="Марта открыла дверь в волшебный сад.",
                approved=True,
            ),
        ],
    )
    stream = BytesIO()
    PILImage.new("RGB", (600, 600), "white").save(stream, "PNG")
    art = {"scene_1": stream.getvalue()}
    pdf = render_illustrated_proof(
        title="Сказка Марты",
        dedication="С любовью",
        graph=graph,
        manuscript=manuscript,
        illustrations=art,
        approved_scene_ids={"scene_1"},
        edition=edition,
    )
    return pdf, art


def test_paid_digital_audit_is_deliverable_without_print_certification():
    pdf, art = _sample("digital")
    report = audit_book_release(
        pdf=pdf, illustrations=art, expected_scenes=1,
        edition="digital", cover_scene_id="scene_1",
    )
    assert report.deliverable
    assert not report.print_ready
    assert report.page_count >= 3
    assert report.illustration_count == 1
    assert "paid_delivery_gate_failed" not in report.issue_codes


def test_editorial_proof_is_not_deliverable():
    pdf, art = _sample("editorial_proof")
    report = audit_book_release(
        pdf=pdf, illustrations=art, expected_scenes=1,
        edition="editorial_proof", cover_scene_id="scene_1",
    )
    assert not report.deliverable
    assert "editorial_proof_not_deliverable" in report.issue_codes


def test_missing_cover_fails_closed():
    pdf, _ = _sample("digital")
    with pytest.raises(ValueError, match="Cover"):
        audit_book_release(
            pdf=pdf, illustrations={}, expected_scenes=1,
            edition="digital", cover_scene_id="scene_1",
        )


def test_invalid_pdf_fails_closed():
    _, art = _sample("digital")
    with pytest.raises(ValueError, match="PDF"):
        audit_book_release(
            pdf=b"not a PDF", illustrations=art, expected_scenes=1,
            edition="digital", cover_scene_id="scene_1",
        )


def test_scene_count_mismatch_fails_closed():
    pdf, art = _sample("digital")
    with pytest.raises(ValueError, match="count"):
        audit_book_release(
            pdf=pdf, illustrations=art, expected_scenes=2,
            edition="digital", cover_scene_id="scene_1",
        )
