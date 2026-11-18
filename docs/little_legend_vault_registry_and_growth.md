# Little Legend — Vault registry and product growth notes

## This increment

PostgreSQL metadata registry, private owner/story counts, expiry-to-deletion-pending batch. The vault table is created by Alembic revision `20261118_0016` in the existing Neon PostgreSQL database. The revision preserves existing story records and does not create a separate database. Run `alembic upgrade head` before deploying the new API.

No upload endpoint, object storage connection, byte-level validation, file deletion worker, backup purge, or legal consent activation exists. An expiry queue changes **database state only**; it is not deletion of a photo. All media processing stays disabled.

## Infrastructure roadmap

1. Validate the Alembic migration against a Neon staging branch, including existing story rows, rollback behavior and schema indexes.
2. Choose S3-compatible private storage with versioning/retention policy explicitly configured and no public ACLs; Railway ephemeral disk must not hold originals.
3. Introduce short-lived signed uploads only after active parental consent and ownership verification. Validate actual bytes, image decode limits, EXIF stripping and content type server-side.
4. Separate originals, approved reference portraits and book derivatives into distinct retention classes. Delete all classes on withdrawal and expiry, including external AI providers when supported.
5. Implement deletion outbox and idempotent worker with leases, retry backoff and audit events. Monitor backlog, oldest pending item, failed deletion count and storage cost.
6. Make privacy-preserving observability the default: no child names, photos, prompts or signed URLs in logs.

## Commercial ideas to validate

- **Instant preview before checkout:** story outline and illustration style preview without a child's photograph, to reduce friction and processing costs.
- **Two packages:** digital illustrated book and print-ready gift edition; offer optional dedication and gift message.
- **Reorder without retaining photos:** allow the parent to retain the non-sensitive story specification, then re-consent and upload again for a new edition.
- **Family bundle:** siblings or grandparents editions with explicit consent for every depicted child.
- **Cost-based pricing:** track image-generation attempts, approved pages, rendering, storage and payment fees per order; alert on margin erosion.
- **Quality assurance gate:** manual parent approval of reference portrait before generating expensive full-book illustrations.

These are product hypotheses, not verified revenue forecasts. Test conversion, rework rate, cost per approved page and privacy deletion completion before scaling.
