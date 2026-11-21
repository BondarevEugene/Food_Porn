"""Premium R2 assembly guards: no media reads before approval validation."""
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.stored_premium_book import assemble_stored_premium_book
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


class FakeStore:
    def __init__(self):
        self.data = {}
        self.reads = []

    def get(self, *, key):
        self.reads.append(key)
        return self.data[key]


def _image():
    from app.little_legend.generated_art_store import illustration_key

    buffer = BytesIO()
    Image.new("RGB", (720, 960), (52, 89, 125)).save(buffer, format="JPEG")
    return buffer.getvalue(), illustration_key


def _setup():
    graph = build_graph(["First scene"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Приключение началось. " * 30,
            approved=True, revision=2,
        )],
    )
    plan = build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["ref-a", "ref-b", "ref-c"],
        chapter_moments=[("A forest path", "A mountain summit")],
    )
    def job(name):
        return IllustrationJob(
            job_id="lli_" + name.ljust(12, "x"),
            owner_id=1, story_id=2, scene_id=name,
            expected_revision=2, estimated_cost_usd=0.05,
            status=JobStatus.COMPLETED,
        )

    cover = job("premium-cover")
    moments = {slot.moment_id: job(slot.moment_id) for slot in plan.illustrations}
    store = FakeStore()
    image, key = _image()
    for item in [cover, *moments.values()]:
        store.data[key(owner_id=1, story_id=2, job_id=item.job_id)] = image
    return store, dict(
        store=store, owner_id=1, story_id=2, title="Марта и лес",
        dedication="Для тебя", graph=graph, manuscript=manuscript,
        plan=plan, cover_job=cover, moment_jobs=moments,
        approved_moment_ids=set(moments), cover_approved=True,
    )


def test_complete_premium_book_reads_three_distinct_private_assets():
    store, params = _setup()
    pdf = assemble_stored_premium_book(**params)
    assert len(store.reads) == 3
    assert len(set(store.reads)) == 3
    reader = PdfReader(BytesIO(pdf))
    assert sum(bool(page.images) for page in reader.pages) == 3


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_owner", "stale", "unapproved"])
def test_invalid_batch_rejected_without_storage_reads(change):
    store, params = _setup()
    if change == "missing":
        params["moment_jobs"].pop("chapter-01-moment-2")
    elif change == "duplicate":
        params["moment_jobs"]["chapter-01-moment-2"] = params["moment_jobs"][
            "chapter-01-moment-1"
        ]
    elif change == "wrong_owner":
        params["cover_job"].owner_id = 999
    elif change == "stale":
        params["moment_jobs"]["chapter-01-moment-1"].expected_revision = 1
    else:
        params["cover_approved"] = False
    with pytest.raises((PermissionError, ValueError)):
        assemble_stored_premium_book(**params)
    assert store.reads == []
