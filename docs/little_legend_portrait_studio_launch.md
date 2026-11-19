# Little Legend — Portrait Studio 2.0: operator launch checklist

This is an **implementation runbook**, not authorization to process children's photos.

## Current production guarantees

- Child-photo upload is disabled in `secure_vault.PHOTO_UPLOAD_ENABLED`.
- The current illustration provider is text-only. It does not accept a real child's face or photo reference.
- Photo consent remains unavailable until the final privacy notice and independent review are complete.
- Private-vault records are metadata. A deletion queue entry is not proof of object deletion.
- `vault_retention_cycle.run_private_retention_cycle` is opt-in; there is **no automatic scheduler**.
- There are two legacy retention implementations (`vault_operations` and `vault_retention_cycle`). **Do not schedule both.** Consolidate on one verified production path before rollout.
- S3 versioning must be disabled for the current erasure adapter. If enabled or suspended, use a separately reviewed version-aware deletion procedure.
- Successful S3 `delete_object` does not guarantee deletion from backups, replicas, processor logs or externally held copies.

## Before enabling photo ingestion

1. Publish final terms, parental consent, operator/FOP details, privacy contact, AI processor list, transfer destinations and retention/deletion notice.
2. Obtain independent legal/privacy and security reviews; configure authenticated owner-only access and rate limits.
3. Implement server-side byte validation (signature, decode, dimensions, decompression bombs), EXIF removal, malware scanning and upload size limits.
4. Connect a private bucket with encryption, no public ACL, restrictive IAM and audit logging; verify deletion semantics.
5. Implement a durable scheduler, lock strategy, alerting and explicit escalation for exhausted retries.
6. Wire consent withdrawal to **all** downstream jobs, queued provider calls, cached images, generated outputs and deletion requests.
7. Add end-to-end integration tests with a disposable private bucket and Neon test database; test crash/retry, concurrent workers and partial failure.
8. Add verified deletion audit, processor deletion requests and backup retention policy.
9. Run a staged security review with test-only synthetic imagery, never real children's photos.
10. Keep `PHOTO_UPLOAD_ENABLED=False` until all launch blockers are resolved and the final release is explicitly approved.

## Operator monitoring

Use `audit_private_vault(session, config=PrivacyLaunchConfig(...))` to inspect aggregate counters.
The audit never includes owner identifiers, child data, object keys or image bytes.
Escalate any `expired_not_deleted`, `exhausted_retries` or `pending_over_24h` result.
Do not treat a green audit as evidence that upload or image processing is available.
