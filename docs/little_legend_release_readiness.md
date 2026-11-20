# Little Legend — Release readiness and operator acceptance

## One owner-scoped read-only release preflight

`GET /little-legend/api/order-quotes/{quote_id}/release-readiness`

The authenticated endpoint returns a structured report for a paid book:
`payment_verified`, `fulfillment_status`, `release_ready`,
`completed_scenes`, `total_scenes`, `blockers` and
`requires_manual_review`.

This report reuses `assess_production`, the same deterministic manuscript
and illustration-revision readiness logic as the PDF worker. It additionally
checks verified payment, fulfillment existence and the final editorial/parent
approval flags. No provider calls, automatic retries, changes to the story,
media, child prose, S3 keys, or payment mutations.

### Common blocker codes

- `payment_not_verified`: signed payment entitlement is missing.
- `fulfillment_not_requested`: no durable paid fulfillment job exists.
- `graph_missing` / `manuscript_missing`: source book incomplete.
- `parent_approval_missing` / `chapter_unapproved`: parent review needed.
- `illustration_job_count_invalid`: missing or duplicated scene job.
- `illustration_incomplete`: queued or unfinished art job.
- `illustration_revision_stale`: art generated for an older chapter.
- `final_parent_editorial_approval_missing`: final approval not recorded.
- `fulfillment_blocked`: inspect operator diagnostics before taking action.

The response deliberately does not include scene text or identifiers in the
blocker list. `requires_manual_review` is advisory; no unsafe automatic
retries are exposed.

## Controlled acceptance

For a dedicated test quote, first verify the parent has granted current text
and image AI consent and a per-story budget has been configured. Run the
conductor and AI workers in their own Railway services. After each stage,
compare the customer journey endpoint and this readiness endpoint.

Before the PDF worker can release a book, readiness must show
`release_ready=true`. Confirm the final PDF is stored privately and Telegram
delivery has a persisted positive message receipt. Repeated payment webhooks
and worker restarts must not create duplicate AI dispatches or duplicate
Telegram sends. Ambiguous external outcomes require manual reconciliation.

This PR is diagnostic and safety-oriented. It does not itself prove an
end-to-end live order has completed.
