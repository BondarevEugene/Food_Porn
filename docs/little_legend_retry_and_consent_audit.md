# Little Legend — Neon deletion retries and consent audit

## Schema migrations

- `20261118_0017`: last/next deletion attempt timestamps and retry-due index
- `20261118_0018`: append-only owner/story consent event journal

Run the normal Alembic migration smoke test before deployment. No existing
private media rows are deleted by these migrations.

## Deletion lifecycle

1. Expired `reserved` and `stored` assets enter `deletion_pending`.
2. Object-store deletion is attempted; only successful calls mark `deleted`.
3. Failures enter `delete_failed`, recording an opaque error code, attempt
   timestamp and next retry time.
4. Retention orchestration requeues failed rows only when the retry timestamp
   is due and a minimum cooldown has elapsed.
5. Aggregate backlog and age metrics remain available to operators.

Backoff starts at 5 minutes and doubles, capped at 24 hours. There is no
hard attempt limit yet: operators must monitor stuck assets. The object
store may be versioned; DeleteObject alone is not proof of complete erasure.

## Consent audit

`append_consent_event` checks story ownership in the insert statement.
`withdraw_and_queue_private_media` records a withdrawal and queues all
eligible private media in the same caller-owned database transaction.
The caller must commit. The worker must subsequently perform physical
deletion. Neither operation enables photo upload or third-party processing.

## Security and launch blockers

- The existing consent policy is still draft and cannot grant photo consent.
- No public API for consent event submission is enabled in this PR.
- Production scheduler, deployment secrets, bucket policies, IAM, storage
  versioning, backups and processor agreements require separate review.
- No child-photo uploads are activated.
- A rollback of the retry migration discards retry scheduling metadata;
  coordinate rollbacks with the deletion worker.
