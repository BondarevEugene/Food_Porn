"""Private generated art and book assembly safety tests."""
from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.generated_art_store import (
    illustration_key,
    save_generated_illustration,
)
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.private_book_assembly import assemble_private_book
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, *, key, data, content_type):
        assert content_type == "image/jpeg"
        self.objects[key] = data

    def get(self, *, key):
        return self.objects[key]


def _jpeg():
    stream = BytesIO()
    Image.new("RGB", (600, 600), "white").save(stream, format="JPEG")
    return stream.getvalue()


def _book():
    graph = build_graph(["The forest opens"])
    manuscript = StoryManuscript(
        hero_name="Marta", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Marta entered the forest.",
            approved=True,
        )],
    )
    job = IllustrationJob(
        job_id="lli_123456789", story_id=2, owner_id=3,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
        provider_dispatched_at=datetime.now(UTC),
    )
    return graph, manuscript, job


def test_generated_art_key_is_deterministic_and_scoped():
    first = illustration_key(owner_id=3, story_id=2, job_id="lli_123456789")
    assert first == illustration_key(
        owner_id=3, story_id=2, job_id="lli_123456789",
    )
    assert first != illustration_key(
        owner_id=4, story_id=2, job_id="lli_123456789",
    )
    assert first.startswith("little-legend/generated/")


def test_assemble_approved_book_from_private_art():
    graph, manuscript, job = _book()
    store = MemoryStore()
    save_generated_illustration(
        store=store, owner_id=3, story_id=2,
        job_id=job.job_id, data=_jpeg(),
    )
    output = assemble_private_book(
        title="Marta", dedication="For you", graph=graph,
        manuscript=manuscript, jobs=[job],
        owner_id=3, story_id=2, store=store,
    )
    assert output.startswith(b"%PDF-")


def test_assembly_rejects_unfinished_jobs_before_storage_access():
    graph, manuscript, job = _book()
    job = job.model_copy(update={"status": JobStatus.RUNNING})
    with pytest.raises(PermissionError, match="completed"):
        assemble_private_book(
            title="Marta", dedication="", graph=graph,
            manuscript=manuscript, jobs=[job],
            owner_id=3, story_id=2, store=MemoryStore(),
        )


def test_assembly_rejects_art_from_old_chapter_revision():
    graph, manuscript, job = _book()
    manuscript.chapters[0].revision = 2
    with pytest.raises(PermissionError, match="completed"):
        assemble_private_book(
            title="Marta", dedication="", graph=graph,
            manuscript=manuscript, jobs=[job],
            owner_id=3, story_id=2, store=MemoryStore(),
        )


def test_private_book_two_approved_scenes_render_real_pdf():
    graph = build_graph(["The forest opens", "Marta finds a path"])
    manuscript = StoryManuscript(
        hero_name="Marta", parent_approved=True,
        chapters=[
            ChapterDraft(scene_id="scene_1", text="The forest opens.", approved=True),
            ChapterDraft(scene_id="scene_2", text="Marta finds a path.", approved=True),
        ],
    )
    store = MemoryStore()
    jobs = []
    for index in (1, 2):
        job = IllustrationJob(
            job_id=f"lli_scene_{index}", story_id=2, owner_id=3,
            scene_id=f"scene_{index}", expected_revision=1,
            estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
            provider_dispatched_at=datetime.now(UTC),
        )
        save_generated_illustration(
            store=store, owner_id=3, story_id=2,
            job_id=job.job_id, data=_jpeg(),
        )
        jobs.append(job)
    pdf = assemble_private_book(
        title="Marta", dedication="For you", graph=graph,
        manuscript=manuscript, jobs=jobs,
        owner_id=3, story_id=2, store=store,
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


def test_private_book_rejects_undispatched_job_without_storage_reads():
    graph, manuscript, job = _book()
    job = job.model_copy(update={"provider_dispatched_at": None})

    class NoReadStore:
        def get(self, *, key):
            pytest.fail("Private storage must not be read before dispatch validation")

    with pytest.raises(PermissionError, match="dispatched"):
        assemble_private_book(
            title="Marta", dedication="", graph=graph,
            manuscript=manuscript, jobs=[job],
            owner_id=3, story_id=2, store=NoReadStore(),
        )


def test_private_book_rejects_duplicate_jobs_before_storage_reads():
    graph, manuscript, job = _book()

    class NoReadStore:
        def get(self, *, key):
            pytest.fail("Private storage must not be read for duplicate jobs")

    with pytest.raises(PermissionError, match="Exactly one"):
        assemble_private_book(
            title="Marta", dedication="", graph=graph,
            manuscript=manuscript, jobs=[job, job.model_copy(deep=True)],
            owner_id=3, story_id=2, store=NoReadStore(),
        )
