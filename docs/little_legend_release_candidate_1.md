# Little Legend — Release Candidate 1.0: acceptance and go/no-go

This release integrates the already-merged production conductor, AI queues,
paid PDF worker, owner-scoped release readiness, production operations and
watchdog into an owner-visible operational view.

## Owner operations

Authenticated `GET /little-legend/api/production/dashboard?limit=50`
shows up to 100 recent **owned** orders, statuses and warning codes.
The endpoint uses the existing Mini CRM authentication dependency and
does not reveal story text, photos, S3 keys or other owners' orders.
It is read-only. For a flagged order, follow the existing endpoints:

- `/little-legend/api/order-quotes/{quote_id}/production-operations`
- `/little-legend/api/order-quotes/{quote_id}/release-readiness`
- `/little-legend/api/order-quotes/{quote_id}/journey`
- `/little-legend/api/order-quotes/{quote_id}/diagnostics`

The overview is **bounded to the newest N orders**, not a historical
all-orders KPI. Its `total_orders` and `attention_required` counts refer
only to the returned page.

## Go/no-go release checklist

1. Deploy the four existing Railway service configurations and run the
   deployment preflight with actual production environment variables.
2. Confirm Neon migrations and S3 read/write permissions from Railway.
3. Keep AI dispatch and paid delivery flags disabled until supervised tests.
4. Create one test story with the parent; verify all text/image consents and
   final approvals, including withdrawal paths.
5. Perform a test-mode payment through the real provider callback and verify
   server-side entitlement; never trust the browser return URL.
6. Run writer and illustrator queues, inspect quality, confirm the parent
   approves the exact revision used for the export.
7. Confirm exactly one PDF is produced and stored privately in S3.
8. Confirm exactly one Telegram delivery, receipt persistence and private
   PDF re-download for the paying owner.
9. Restart each Railway worker between durable stages; verify no duplicate
   AI dispatch, budget capture or Telegram send.
10. Deliberately inject an expired lease and an uncertain provider outcome;
    ensure operator review is required, not automatic retries.
11. Check watchdog output and the owner dashboard for corresponding alerts.
12. Enable production traffic only after checks 1–11 pass, with rollback
    settings and operator access documented.

## Explicitly not certified by green CI

CI runs deterministic tests and migration smoke checks. It does not prove
live provider availability, Railway deployment, real paid checkout, OpenAI
quality, Telegram receipt or physical print fulfillment. Print is outside
the digital-edition release scope. These require supervised acceptance.

## Operational rollback

Disable conductor and AI runner flags first, preserve database and S3 assets,
and keep all ambiguous ledger effects and delivery claims intact. Never
clear a stale lease or held AI budget merely to make a queue move.
