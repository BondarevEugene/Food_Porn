# Little Legend Secure Photo Vault — foundation v1

**This PR does not store photographs.** The current module is a fail-closed domain foundation: metadata contracts, retention policy, state transitions and ownership checks. Photo upload and retrieval endpoints do not exist.

## Implemented

- Opaque random 192-bit asset IDs and non-public object key conventions.
- Per-owner and per-story authorization helper.
- Input envelope limits (JPEG/PNG/WebP, max 12 MiB, max 24 million pixels). These limits apply to declared metadata only, not actual bytes.
- Default 7-day retention; maximum 30-day retention; expiration detection.
- Explicit reserved/stored/deletion pending/deleted/deletion failed states and retry accounting.
- Read-only, owner-scoped API reporting vault capability as **disabled**.
- Tests without real child images.

## Required before first actual upload

1. Select and configure durable private object storage compatible with Railway restarts (do not rely on ephemeral local disk).
2. Verify file magic bytes, decode safely with bounded resources, normalize and strip EXIF, reject dangerous/unsupported payloads.
3. Store encrypted objects using server-side keys, private bucket, no public URLs, signed access only after story ownership and active parental consent checks.
4. Persist vault asset rows and deletion attempts in PostgreSQL using Alembic migration; implement transactional upload reservation and crash recovery.
5. Implement an idempotent worker to delete originals, derivatives and expired assets, with external processor deletion confirmation and backup retention policy.
6. Validate privacy documents and provider agreements for the Ukrainian FOP, disclose transfers and retention, obtain independent security/legal review.
7. Add integration tests for cross-owner IDOR, revoked consent, failed writes, restarts, retention and orphan cleanup.
8. Enable photo upload only in a separate reviewed release. Current `PHOTO_UPLOAD_ENABLED` must remain `False`.

Do not claim that deletion-state transitions actually delete files: storage and worker integration are not implemented yet.
