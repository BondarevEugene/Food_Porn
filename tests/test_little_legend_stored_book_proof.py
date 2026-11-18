"""Stored proof assembly must fail before accessing private assets."""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.stored_book_proof import assemble_stored_book_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue import JobStatus


def test_stored_proof_rejects_incomplete_manuscript_without_storage_access():
    store = Mock()
    graph = build_graph(["Forest"])
    manuscript = StoryManuscript(hero_name="Marta")
    with pytest.raises(PermissionError, match="approved manuscript"):
        assemble_stored_book_proof(
            store=store, owner_id=2, story_id=3, title="Forest",
            dedication="", graph=graph, manuscript=manuscript, jobs=[],
        )
    store.get.assert_not_called()


def test_stored_proof_rejects_foreign_job_without_storage_access():
    store = Mock()
    graph = build_graph(["Forest"])
    manuscript = Mock(parent_approved=True, chapters=[
        Mock(scene_id="scene_1", approved=True, revision=1),
    ])
    job = IllustrationJob(
        job_id="lli_test123", owner_id=999, story_id=3,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    with pytest.raises(PermissionError, match="ownership"):
        assemble_stored_book_proof(
            store=store, owner_id=2, story_id=3, title="Forest",
            dedication="", graph=graph, manuscript=manuscript, jobs=[job],
        )
    store.get.assert_not_called()
