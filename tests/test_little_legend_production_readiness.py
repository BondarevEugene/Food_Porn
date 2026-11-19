"""Production readiness covers approvals, revision integrity and export gates."""
from datetime import UTC, datetime

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.production_readiness import assess_production
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


def _production():
    graph = build_graph(["Forest opens", "A secret door appears"])
    manuscript = StoryManuscript(
        hero_name="Marta", parent_approved=True,
        chapters=[
            ChapterDraft(scene_id=f"scene_{index}", text="A new adventure.",
                         approved=True)
            for index in (1, 2)
        ],
    )
    jobs = [
        IllustrationJob(
            job_id=f"lli_scene_{index}", owner_id=3, story_id=2,
            scene_id=f"scene_{index}", expected_revision=1,
            estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
            provider_dispatched_at=datetime.now(UTC),
        )
        for index in (1, 2)
    ]
    return graph, manuscript, jobs


def test_complete_book_ready_for_export_and_delivery():
    graph, manuscript, jobs = _production()
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=True, pdf_verified=True,
    )
    assert report.ready_for_export
    assert report.ready_for_delivery
    assert report.completed_scenes == report.total_scenes == 2
    assert report.issues == []


def test_verified_pdf_required_for_delivery_but_not_export():
    graph, manuscript, jobs = _production()
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=True,
    )
    assert report.ready_for_export
    assert not report.ready_for_delivery
    assert [issue.code for issue in report.issues] == ["pdf_not_verified"]


def test_stale_illustration_and_unapproved_editorial_block_export():
    graph, manuscript, jobs = _production()
    manuscript.chapters[0].revision = 2
    report = assess_production(graph=graph, manuscript=manuscript, jobs=jobs)
    assert not report.ready_for_export
    assert not report.ready_for_delivery
    assert "illustration_revision_stale" in {issue.code for issue in report.issues}
    assert "editorial_approval_missing" in {issue.code for issue in report.issues}


def test_duplicate_and_foreign_scene_jobs_block_export():
    graph, manuscript, jobs = _production()
    jobs.append(jobs[0].model_copy(deep=True))
    jobs.append(jobs[1].model_copy(update={"scene_id": "other"}))
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=True, pdf_verified=True,
    )
    assert not report.ready_for_export
    assert "illustration_job_count_invalid" in {issue.code for issue in report.issues}
    assert "unexpected_illustration" in {issue.code for issue in report.issues}


def test_missing_parent_approval_blocks_publication():
    graph, manuscript, jobs = _production()
    manuscript.parent_approved = False
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=True, pdf_verified=True,
    )
    assert not report.ready_for_export
    assert "parent_approval_missing" in {issue.code for issue in report.issues}
