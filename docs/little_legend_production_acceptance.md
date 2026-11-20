# Little Legend — Production Acceptance

This checklist is not evidence of a successful production order. Use an isolated test owner and explicit small AI budget.

## Before launch

1. Confirm deployed Git SHA, Alembic head, green Ruff, pytest and migration smoke checks.
2. Confirm Neon, Railway, Telegram, private PDF and art stores, provider configuration and consent disclosures. Never print secrets.
3. Confirm test order price, payment state and estimated provider costs before any billable request.

## End-to-end acceptance

1. Create a story in private Telegram chat, complete guided intake, approve outline.
2. Start writing once; verify saved chapter texts and duplicate enqueue protection.
3. Read and approve every chapter; final approval must be blocked for missing or unapproved chapters.
4. Confirm image AI consent and budget; enqueue illustration batch once, check revision binding.
5. Verify actual images in private storage, image validity and no stale revisions.
6. Complete editorial decision; production readiness must show no blockers before PDF assembly.
7. Assemble PDF; verify stored bytes, SHA-256, page count, typography, illustration layout and portrait safety.
8. Deliver PDF once to the owner; verify Telegram message ID and Neon delivery state.
9. Repeat the send callback; verify no duplicate PDF delivery.

## Fault injection

- Wrong owner cannot access story, writer, art, PDF or delivery.
- Revoked consent blocks provider dispatch.
- Expired lease or uncertain provider result never triggers blind paid retry.
- Interrupted PDF assembly cannot create a false READY release.
- Ambiguous Telegram send must be reconciled manually, not automatically resent.
- Restart worker between stages and verify recovery from durable Neon state.

## Release decision

Record deployed SHA, test story ID, migration head, paid request count, costs, release fingerprint, PDF hash and Telegram message ID in a private acceptance record. Redact child content and secrets.

**GO** only if all critical checks pass. Otherwise **NO-GO**, with failing stage documented.
