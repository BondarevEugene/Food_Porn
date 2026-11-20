# Little Legend — paid production conductor

This service advances a **verified paid order** through existing AI queues,
without granting parent consent or editorial approval.

Start a separate Railway worker service with:

```sh
python -m app.little_legend.production_conductor
```

Set `LL_CONDUCTOR_ENABLED=true` and a positive
`LL_ILLUSTRATION_PRICE_MICRO_USD`. Use the same Neon database as the bot
and the existing writer, illustration, and PDF delivery workers.

## What happens

1. A verified WayForPay receipt creates a pending fulfillment job.
2. The conductor waits for an approved parent-sourced outline and valid
   text-AI consent, then enqueues chapter jobs using the existing transactional
   enqueue implementation.
3. The writer worker creates chapters. Parent review and approval are required.
4. After the complete manuscript is parent-approved and image-AI consent is
   valid, the conductor enqueues the illustration batch.
5. The illustration worker saves approved assets in private S3.
6. The existing paid PDF worker waits for final editorial and parent approvals,
   then assembles the book and delivers it through Telegram.

The conductor requires a preconfigured per-story AI budget. Missing budgets
and invalid/uncertain state **do not** authorize billable work. All underlying
enqueue functions recheck owner scope, consent, approvals and duplicate jobs.
The conductor never calls a provider and never retries dispatched AI effects.

Run `python -m app.little_legend.production_conductor --once` to inspect one
controlled queue scan. This command can **enqueue** billable work for active
AI workers; do not enable it on a live database until payment, consent,
pricing, budget, and data-retention policies have been reviewed.

Known limitation: completed writer jobs do not imply manuscript approval.
Manual parent review remains mandatory. Failed or ambiguous AI jobs require
operator reconciliation; the conductor does not reset them.
