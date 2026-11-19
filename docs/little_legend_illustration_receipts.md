# Little Legend image worker receipts

The illustration provider retains the existing `generate_scene() -> bytes`
interface. The one-shot illustration runner uses the new optional
`generate_scene_with_receipt()` interface to pass image bytes and a provider
receipt through the worker pipeline.

Order of operations: consent/approval check -> durable dispatch fence ->
one provider call -> image sanitation -> private asset persistence ->
queue completion and budget settlement in one database transaction.

Optional `LL_ILLUSTRATION_USD_PER_IMAGE` is an **operator-verified USD
per generated image** amount, not a customer price or queue estimate. It
must reflect the selected model, quality, size and current provider billing.
When unset, or when the provider does not return a response ID, the worker
completes without a charge receipt and retains the financial hold for
manual reconciliation. Never fabricate a provider response ID.

Do not enable fixed-price settlement for a variable-cost image model or
when the provider's pricing differs from the configured amount. A returned
image is not proof of a final provider invoice.

This change does not automatically start the illustration worker, does not
perform customer delivery, and does not assert full end-to-end production.
