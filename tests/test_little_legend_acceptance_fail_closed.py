"""Regression gates for incomplete Little Legend releases (no paid calls)."""
from app.little_legend.production_readiness import assess_production
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _report(*, parent_approved: bool, chapters_approved: bool):
    graph = build_graph(["Начало", "Финал"])
    manuscript = StoryManuscript(
        hero_name="Оля",
        chapters=[
            ChapterDraft(
                scene_id=node.id, text=f"Глава {node.order}",
                approved=chapters_approved,
            )
            for node in graph.nodes
        ],
        parent_approved=parent_approved,
    )
    return assess_production(
        graph=graph, manuscript=manuscript, jobs=[],
        editorial_approved=True,
    )


def test_complete_text_without_art_cannot_be_exported():
    report = _report(parent_approved=True, chapters_approved=True)
    assert not report.ready_for_export
    assert not report.ready_for_delivery
    assert any(
        issue.code == "illustration_job_count_invalid"
        for issue in report.issues
    )


def test_final_parent_approval_cannot_be_inferred_from_chapters():
    report = _report(parent_approved=False, chapters_approved=True)
    assert not report.ready_for_export
    assert any(issue.code == "parent_approval_missing" for issue in report.issues)


def test_individual_chapter_approval_is_mandatory():
    report = _report(parent_approved=True, chapters_approved=False)
    assert not report.ready_for_export
    assert any(issue.code == "chapter_unapproved" for issue in report.issues)


def test_pdf_is_unverified_until_explicitly_verified():
    report = _report(parent_approved=True, chapters_approved=True)
    assert not report.ready_for_delivery
    assert any(issue.code == "pdf_not_verified" for issue in report.issues)
