"""End-to-end premium PDF assembly with private generated artwork."""

from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.generated_art_store import illustration_key
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_book_pdf import (
    assemble_premium_book_pdf,
    validate_premium_book_jobs,
)
from app.little_legend.premium_queue_safety import premium_story_fingerprint
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.router import router
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


class FakeArtStore:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.reads = []

    def get(self, *, key: str) -> bytes:
        self.reads.append(key)
        return self.data


def book():
    graph = build_graph(["Герой отправляется в путь"])
    manuscript = StoryManuscript(
        hero_name="Оля",
        chapters=[ChapterDraft(
            scene_id=graph.nodes[0].id, text="Жила-была девочка Оля. Она нашла карту.",
            approved=True, revision=1,
        )],
        parent_approved=True,
    )
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE,
        reference_ids=["private-ref"],
        chapter_moments=[("Встреча с картой", "Открытие волшебной двери")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=42, story_id=7, plan=plan, chapter_revisions=[1],
    )
    fingerprint = premium_story_fingerprint(graph=graph, manuscript=manuscript)
    jobs = [
        IllustrationJob(
            job_id=f"lli_{index}", owner_id=42, story_id=7,
            scene_id=req.moment_id, status=JobStatus.COMPLETED,
            expected_revision=req.expected_revision,
            estimated_cost_usd=req.estimated_micro_usd / 1_000_000,
            premium_manifest_fingerprint=manifest.fingerprint,
            premium_story_fingerprint=fingerprint,
            premium_manifest_snapshot=manifest.model_dump(mode="json"),
            premium_plan_snapshot=plan.model_dump(mode="json"),
        )
        for index, req in enumerate(manifest.requests)
    ]
    return graph, manuscript, jobs


def test_premium_pdf_contains_all_distinct_generated_images() -> None:
    graph, manuscript, jobs = book()
    image = Image.new("RGB", (400, 400), "white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    store = FakeArtStore(buffer.getvalue())
    pdf = assemble_premium_book_pdf(
        store=store, owner_id=42, story_id=7,
        title="Волшебная история", dedication="Для Оли",
        graph=graph, manuscript=manuscript, jobs=jobs,
    )
    assert pdf.startswith(b"%PDF-")
    assert len(store.reads) == 3
    assert store.reads == [
        illustration_key(owner_id=42, story_id=7, job_id=job.job_id)
        for job in jobs
    ]


@pytest.mark.parametrize("remove", [0, 1, 2])
def test_missing_premium_moment_fails_before_storage_read(remove: int) -> None:
    graph, manuscript, jobs = book()
    with pytest.raises(PermissionError):
        validate_premium_book_jobs(
            owner_id=42, story_id=7, graph=graph,
            manuscript=manuscript,
            jobs=[job for index, job in enumerate(jobs) if index != remove],
        )


def test_cross_owner_and_stale_story_are_rejected() -> None:
    graph, manuscript, jobs = book()
    with pytest.raises(PermissionError):
        validate_premium_book_jobs(
            owner_id=43, story_id=7, graph=graph,
            manuscript=manuscript, jobs=jobs,
        )
    manuscript.chapters[0].text = "Изменённая рукопись"
    with pytest.raises(PermissionError):
        validate_premium_book_jobs(
            owner_id=42, story_id=7, graph=graph,
            manuscript=manuscript, jobs=jobs,
        )


def test_premium_pdf_download_route_is_authenticated() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "").endswith("/illustrations/premium-book.pdf")
    )
    assert "GET" in route.methods
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)
