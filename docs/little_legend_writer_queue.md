# Little Legend — writer queue policy (phase 1)

This PR implements a pure, serializable state machine for generation jobs.
It does **not** yet start workers, enqueue jobs, create database tables, or
call OpenAI. Deployment is inert until a durable store and worker are wired.

Each job binds a story, owner, scene, expected manuscript revision, unique
job ID and estimated cost. Claims use unique lease tokens. Expired claims
may be reclaimed, with a bounded retry budget. Errors retry with exponential
backoff. Completed and cancelled jobs cannot be claimed again.

**Required for production integration**
1. Add an Alembic migration for a dedicated job table in Neon PostgreSQL.
2. Use an atomic compare-and-swap or SELECT FOR UPDATE SKIP LOCKED transaction
   to claim jobs and persist each state transition.
3. Verify the owner and provider-processing consent before any external call.
4. Atomically check the lease token and manuscript revision when saving a
   checkpoint; a stale worker must not commit text after its lease expires.
5. Track actual provider spend as well as estimates; enforce per-order and
   daily budgets. Add concurrency limits, cancellation and operational alerts.
6. Persist queue state across Railway restarts and run a separate worker.
7. Do not enable children's photo uploads or third-party image processing.

This phase deliberately makes no claim of crash-safe execution yet; only
the state-transition rules and their tests are delivered.
