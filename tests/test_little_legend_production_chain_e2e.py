"""Full Little Legend production contract, using real PDF rendering and fake S3.

No external providers, payments, database writes, Telegram messages or R2
credentials. All objects are synthetic and isolated to this test.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfReader

from app.little_legend.generated_art_store import (
    GeneratedArtS3Settings,
    S3GeneratedArtStore,
    illustration_key,
)
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.paid_book_storage import PaidBookStore, pdf_key
from app.little_legend.release_quality_engine import audit_book_release
from app.little_legend.stored_book_proof import assemble_stored_book_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus

OWNER = 42
STORY = 73
QUOTE = 91


class _Body(BytesIO):
    pass


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.fail_next_get = False
        self.corrupt_next_get = False

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        assert kwargs.get("CacheControl") == "private, no-store"
        assert "ACL" not in kwargs
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, *, Bucket, Key):
        if self.fail_next_get:
            self.fail_next_get = False
            raise ConnectionError("simulated interrupted storage read")
        data = self.objects[(Bucket, Key)]
        if self.corrupt_next_get:
            self.corrupt_next_get = False
            data = b"corrupted"
        return {"Body": _Body(data)}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def stores(monkeypatch):
    import boto3

    backend = MemoryS3()
    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: backend)
    settings = GeneratedArtS3Settings(
        endpoint_url="https://r2.example.invalid",
        bucket="private", region="auto",
        access_key_id="fake", secret_access_key="fake",
    )
    art = S3GeneratedArtStore(settings)
    for key, value in {
        "LITTLE_LEGEND_S3_ENDPOINT_URL": "https://r2.example.invalid",
        "LITTLE_LEGEND_S3_BUCKET": "private",
        "LITTLE_LEGEND_S3_REGION": "auto",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID": "fake",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY": "fake",
    }.items():
        monkeypatch.setenv(key, value)
    return backend, art, PaidBookStore()


def _jpeg(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (700, 700), color).save(output, format="JPEG")
    return output.getvalue()


def _book_inputs(scene_count=2):
    graph = build_graph([f"Приключение {i}" for i in range(scene_count)])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[
            ChapterDraft(
                scene_id=node.id,
                text=("Марта открыла волшебную дверь. " * 12).strip(),
                approved=True, revision=1,
            )
            for node in graph.nodes
        ],
    )
    jobs = [
        IllustrationJob(
            job_id=f"lli_synthetic_{i}",
            owner_id=OWNER, story_id=STORY,
            scene_id=node.id, expected_revision=1,
            estimated_cost_usd=0.05,
            status=JobStatus.COMPLETED,
            provider_dispatched_at=datetime.now(UTC),
        )
        for i, node in enumerate(graph.nodes)
    ]
    return graph, manuscript, jobs


def _upload_art(art, jobs):
    images = {}
    for i, job in enumerate(jobs):
        data = _jpeg(["#8db8ee", "#f5b8cf", "#b5d9b4"][i % 3])
        key = illustration_key(
            owner_id=OWNER, story_id=STORY, job_id=job.job_id,
        )
        art.put(key=key, data=data, content_type="image/jpeg")
        images[job.scene_id] = data
    return images


def _assemble(art, graph, manuscript, jobs):
    return assemble_stored_book_proof(
        store=art, owner_id=OWNER, story_id=STORY,
        title="Волшебная история Марты", dedication="С любовью",
        graph=graph, manuscript=manuscript, jobs=jobs,
        edition="digital", palette="lavender",
    )


def test_full_art_to_pdf_to_private_storage_roundtrip(stores):
    backend, art, books = stores
    graph, manuscript, jobs = _book_inputs()
    images = _upload_art(art, jobs)
    assert len(backend.objects) == len(jobs)

    pdf = _assemble(art, graph, manuscript, jobs)
    audit = audit_book_release(
        pdf=pdf, illustrations=images,
        expected_scenes=len(jobs), edition="digital",
        cover_scene_id=graph.nodes[0].id,
    )
    assert audit.deliverable, audit.issue_codes
    assert not audit.print_ready
    assert audit.illustration_count == len(jobs)

    reader = PdfReader(BytesIO(pdf), strict=True)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Марта" in text
    assert "Волшебная история" in text
    assert sum(bool(page.images) for page in reader.pages[2:]) >= len(jobs)

    key = pdf_key(quote_id=QUOTE, owner_id=OWNER)
    books.put(key=key, data=pdf)
    restored = books.get(key=key)
    assert restored == pdf
    assert hashlib.sha256(restored).digest() == hashlib.sha256(pdf).digest()
    assert len(backend.objects) == len(jobs) + 1
    assert all(bucket == "private" for bucket, _ in backend.objects)


def test_interrupted_read_can_resume_without_regeneration(stores):
    backend, art, books = stores
    graph, manuscript, jobs = _book_inputs(scene_count=1)
    _upload_art(art, jobs)
    backend.fail_next_get = True
    with pytest.raises(ConnectionError, match="interrupted"):
        _assemble(art, graph, manuscript, jobs)
    assert len(backend.objects) == 1
    pdf = _assemble(art, graph, manuscript, jobs)
    key = pdf_key(quote_id=QUOTE, owner_id=OWNER)
    books.put(key=key, data=pdf)
    assert books.get(key=key) == pdf


def test_corrupted_art_blocks_release_before_pdf_upload(stores):
    backend, art, books = stores
    graph, manuscript, jobs = _book_inputs(scene_count=1)
    _upload_art(art, jobs)
    backend.corrupt_next_get = True
    with pytest.raises(ValueError, match="illustration"):
        _assemble(art, graph, manuscript, jobs)
    assert not any(key.endswith(".pdf") for _, key in backend.objects)


def test_stale_revision_blocks_storage_reads(stores):
    backend, art, _ = stores
    graph, manuscript, jobs = _book_inputs(scene_count=1)
    _upload_art(art, jobs)
    stale = jobs[0].model_copy(update={"expected_revision": 2})
    with patch.object(art, "get", side_effect=AssertionError("unexpected R2 read")):
        with pytest.raises(PermissionError, match="revision"):
            _assemble(art, graph, manuscript, [stale])
    assert len(backend.objects) == 1


def test_foreign_illustration_key_is_rejected(stores):
    _, art, _ = stores
    with pytest.raises(ValueError, match="key"):
        art.get(key="little-legend/generated/../../other.jpg")


def test_pdf_integrity_failure_is_detected(stores):
    backend, art, books = stores
    graph, manuscript, jobs = _book_inputs(scene_count=1)
    _upload_art(art, jobs)
    pdf = _assemble(art, graph, manuscript, jobs)
    key = pdf_key(quote_id=QUOTE, owner_id=OWNER)
    books.put(key=key, data=pdf)
    backend.objects[("private", key)] = b"invalid"
    with pytest.raises(ValueError, match="PDF"):
        books.get(key=key)
