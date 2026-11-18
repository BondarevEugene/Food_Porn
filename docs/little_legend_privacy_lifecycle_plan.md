# Little Legend — privacy lifecycle release plan

This PR introduces **metadata-only safeguards**, not actual photo storage or deletion.

## Implemented

- Revoking child-photo consent clears stored visual identity's `parental_photo_consent` and `portrait_review` flags atomically with consent state in the story row.
- Preserves parent-authored character descriptions and portrait settings (not photos) for continued editing.
- Exposes authenticated, owner-scoped `GET /little-legend/api/stories/{story_id}/privacy-readiness`.
- Presents a visible readiness checklist. All photo-processing capability flags remain hard-disabled.
- Prevents a concurrent terms update from being based on a stale consent record by evaluating the decision under the database row lock.

## Not implemented; do not claim otherwise

- Uploads, media object storage, encryption/key rotation, media access controls
- Actual deletion of images, derivatives, CDN caches, backups or third-party provider copies
- Verified legal guardian authority, finalized legal notices, signed processor agreements
- Image generation, portrait similarity scoring or automated biometric analysis

## Next secure media phase — requirements

1. Finalize FOP legal identity, data protection contact, privacy policy, provider register, transfer and retention rules.
2. Define a private media backend with per-user ownership, MIME signature validation, byte and pixel limits, malicious payload rejection, non-public keys and bounded retention.
3. Keep uploads disabled by default; use server-side authorization for every object read/write/delete.
4. Implement idempotent deletion jobs with an audit trail, including processor deletion requests and backup expiry; distinguish deletion requested, local deletion completed, and external deletion confirmed.
5. Run threat-model review and tests for IDOR, cross-user access, consent withdrawal races, replay, excessive uploads, orphan cleanup, and logging of personal data.
6. Enable child-photo processing only after all legal and technical gates are independently verified.

**Avoid placing child photographs or sensitive image-derived metadata in JSON story drafts or GitHub logs.**
