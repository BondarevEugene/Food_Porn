"""Billable AI calls must never be retried automatically after ambiguity."""
from types import SimpleNamespace

import pytest

from app.little_legend import sketch_worker
from app.little_legend.writer_queue import JobPolicy, WriterJob, claim_job


def leased_job():
    return claim_job(
        WriterJob(
            job_id="ll_test_ambiguous_provider_12345",
            story_id=1, owner_id=2, scene_id="scene_1",
            expected_revision=0, estimated_cost_usd=0.05,
        ),
        token="test-lease-token-123456789", policy=JobPolicy(),
    )


@pytest.mark.asyncio
async def test_provider_timeout_requires_manual_review(monkeypatch):
    job = leased_job()
    transitions = []

    async def claim(_policy):
        return job

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, *_args):
            return SimpleNamespace(scalar_one_or_none=lambda: "{}")

    class Provider:
        async def write_chapter(self, _brief):
            raise TimeoutError("provider might have billed")

    async def transition(**kwargs):
        transitions.append(kwargs)

    monkeypatch.setattr(sketch_worker, "claim_next_writer_job", claim)
    monkeypatch.setattr(sketch_worker, "async_session_maker", FakeSession)
    monkeypatch.setattr(sketch_worker, "prepare_claimed_chapter", lambda *_: {})
    monkeypatch.setattr(sketch_worker, "transition_writer_job", transition)
    result = await sketch_worker.run_one_writer_job(Provider())
    assert result["status"] == "manual_review"
    assert transitions[0]["retryable"] is False
    assert transitions[0]["error_code"] == "provider_outcome_unknown"
