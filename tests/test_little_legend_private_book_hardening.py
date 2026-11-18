"""Regression guards for the private illustrated PDF assembly boundary."""
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.private_book_assembly import assemble_private_book
from app.little_legend.story_graph import build_graph
from app.little_legend.writer_queue import JobStatus


def _job(*, owner_id=2, dispatched=True):
    return IllustrationJob(
        job_id="lli_test123", owner_id=owner_id, story_id=3,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
        provider_dispatched_at=datetime.now(UTC) if dispatched else None,
    )


def _manuscript():
    return Mock(parent_approved=True, chapters=[
        Mock(scene_id="scene_1", approved=True, revision=1),
    ])


def _assemble(store, jobs, manuscript=None):
    return assemble_private_book(
        store=store, owner_id=2, story_id=3, title="Forest",
        dedication="", graph=build_graph(["Forest"]),
        manuscript=manuscript or _manuscript(), jobs=jobs,
    )


def test_private_book_rejects_foreign_completed_art_before_read():
    store = Mock()
    with pytest.raises(PermissionError, match="ownership"):
        _assemble(store, [_job(owner_id=99)])
    store.get.assert_not_called()


def test_private_book_rejects_duplicate_scene_jobs_before_read():
    store = Mock()
    with pytest.raises(PermissionError, match="Exactly one"):
        _assemble(store, [_job(), _job()])
    store.get.assert_not_called()


def test_private_book_rejects_undispatched_job_before_read():
    store = Mock()
    with pytest.raises(PermissionError, match="dispatched"):
        _assemble(store, [_job(dispatched=False)])
    store.get.assert_not_called()


def test_private_book_rejects_unapproved_manuscript_before_read():
    store = Mock()
    manuscript = _manuscript()
    manuscript.parent_approved = False
    with pytest.raises(PermissionError, match="approved manuscript"):
        _assemble(store, [_job()], manuscript)
    store.get.assert_not_called()
