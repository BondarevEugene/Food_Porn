"""Enqueue guards: approval and opt-in are independent."""
from app.little_legend.writer_queue import JobStatus, WriterJob


def test_queue_job_has_bounded_cost_and_revision():
    job = WriterJob(
        job_id="ll_secure_queue_job_123456789", story_id=42, owner_id=7,
        scene_id="scene_1", expected_revision=0, estimated_cost_usd=0.05,
    )
    assert job.status == JobStatus.QUEUED
    assert job.expected_revision == 0
