# Little Legend — Production Watchdog

The watchdog is an **operator-only read-only diagnostic**, not a retry worker.
It reports counts of suspicious production states from the same Neon database
used by the Little Legend conductor, AI workers and PDF worker.

## Run

From a trusted Railway shell in the existing project:

```bash
python -m app.little_legend.production_watchdog
```

The process returns JSON with `checked_at`, `total_fulfillment_jobs`,
`alerts`, `requires_operator`, and `automatic_retry_allowed=false`.

Exit code `0` means no tracked anomalies; `2` means operator action is
required. Database connectivity errors fail the command; they are **not**
reported as healthy. The output deliberately contains **no child story,
scene, owner, quote, S3 key, Telegram recipient, or payment identifier**.

## Alerts and operator response

| Alert | What it means | Safe response |
| --- | --- | --- |
| `stale_pdf_lease` | PDF job is processing with expired/missing lease | Check asset and lease records; never auto-reclaim |
| `delivery_unconfirmed` | Telegram send claimed, no durable receipt | Reconcile Telegram before any resend |
| `blocked_fulfillment` | PDF production failed or blocked | Inspect quote's owner-scoped release-readiness |
| `old_pending` | Pending job older than 60 minutes | Check gates, worker health and deployment |
| `unresolved_ai_effects` | AI ledger has reserved/dispatched/uncertain effects | Reconcile provider usage and receipts |
| `held_ai_budget` | Money reserved for unresolved provider effects | Reconcile before settling/releasing |
| `budget_overcommitted` | Held plus spent exceeds configured limit | Stop further billable dispatch and investigate |

Counts are independent: one job can contribute to multiple alerts. Old
pending work may legitimately be waiting for approval; it is a signal to
inspect, not evidence that the worker is broken.

## Operational constraints

- No automatic AI retries, Telegram resends, budget releases or approvals.
- Do not expose the command as a public HTTP endpoint.
- Run it manually from Railway first; only add periodic scheduling after
  establishing a secure operator notification destination and rate limits.
- CI unit tests exercise the classifications without requiring Neon.
- A green CI check is not a substitute for a supervised paid test order.
