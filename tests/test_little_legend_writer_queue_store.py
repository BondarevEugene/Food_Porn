"""Schema and durable queue safety invariants."""
from app.little_legend.writer_queue import JobStatus
from app.little_legend.writer_queue_store import writer_jobs


def test_queue_schema_contains_owner_and_lease_payload():
    assert writer_jobs.name == "little_legend_writer_jobs"
    assert writer_jobs.c.job_id.primary_key
    assert not writer_jobs.c.owner_id.nullable
    assert not writer_jobs.c.payload.nullable
    assert not writer_jobs.c.status.nullable


def test_queue_states_are_persistable_strings():
    assert {state.value for state in JobStatus} == {
        "queued", "running", "retry_wait",
        "completed", "failed", "cancelled",
    }
