# Little Legend — Neon-backed job queue, phase 2

The `little_legend_writer_jobs` table is created by the existing Little
Legend schema initializer (alongside `little_legend_stories`).
This matches the existing module's schema lifecycle and does not require
a separate Alembic revision. Production deployment must run schema
initialization before starting a worker.

## Internal store API

- `enqueue_writer_job(job)`: requires a fresh queued job and validates
  story ownership in the same database transaction
- `claim_next_writer_job(policy)`: uses PostgreSQL
  `SELECT FOR UPDATE SKIP LOCKED` and a cryptographically random lease token
- `transition_writer_job(...)`: owner- and token-checked state transition
- `cancel_queued_writer_job(...)`: owner-checked cancellation

The payload and status are committed together. Multiple workers cannot
claim the same row concurrently. Expired leases can be reclaimed under
the bounded retry policy.

## Remaining gates before enabling AI

**Do not enable a worker yet.** The worker must validate explicit
provider-processing consent and enforce an actual-spend budget. It must
commit chapter checkpoints only while holding the current lease; the
existing checkpoint API alone does not enforce that lease. Job creation
must validate scene IDs, current chapter revision and approved locks.
Add a recovery path for exhausted expired leases and status/progress UI.
No child-photo processing is enabled.
