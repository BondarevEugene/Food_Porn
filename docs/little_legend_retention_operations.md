# Little Legend — private media retention operations

This PR adds a manual, **opt-in** retention cycle, not an active production scheduler.

## Transaction boundaries

1. Queue expired records using PostgreSQL row locks, then commit.
2. Delete queued private objects using the existing guarded deletion worker, then commit.
3. Query aggregate health counts and the age of the oldest pending deletion.

Call `run_retention_cycle(session_factory, store)` only from a trusted
operator-controlled job after configuring a private bucket, IAM restrictions,
timeouts, monitoring and a vetted privacy policy. Never expose this function
as an unauthenticated HTTP endpoint.

## Owner deletion requests

`queue_story_deletion(session, owner_id=..., story_id=...)` queues matching
assets for deletion. It does not erase bytes by itself. Callers must commit
and ensure the deletion worker subsequently processes the queue.

## Known blockers

- No automatic scheduler, no retry cooldown timestamp and no dead-letter policy.
- Existing expiry queue can requeue failed rows immediately after expiry.
  The new `requeue_failed_deletions` deliberately does nothing until a
  timestamped retry/backoff migration exists.
- Object-store calls are synchronous and occur while DB row locks are held.
  Set strict network timeouts and keep batches small before production use.
- No upload endpoint or parent consent activation.
- Successful S3 DeleteObject does not by itself prove removal of object
  versions, replicas or provider backups; review bucket versioning and lifecycle.
- Metrics are aggregate-only and should be alerted on, not shown to customers
  as proof of erasure.

## Next implementation

Add `last_deletion_attempt_at` and `next_deletion_attempt_at` in Alembic,
exponential backoff, bounded attempts, version-aware deletion, durable consent
records, withdrawal-to-queue integration, and an operational scheduler.
