# Little Legend: illustration provider settlement

The OpenAI image adapter retains its original `generate_scene(...)->bytes`
API for existing callers and adds `generate_scene_with_receipt(...)` for
the production worker.

Set `LL_ILLUSTRATION_PRICE_MICRO_USD` only after verifying the current
**per-image** price for the configured model, size and quality against the
provider's billing. This value is an operator-controlled estimate based on
published pricing, **not a provider-reported charge**. For that reason it
must not be treated as independently verified usage. In particular, the
image API may omit a response ID: in that case no receipt is emitted, and
the budget reservation remains held for manual reconciliation.

The worker sanitizes and privately persists the image before attempting
queue completion. If a complete provider acknowledgement is available,
completion and financial settlement occur in the same DB transaction.
An ambiguous response, failed storage write or lease loss must never cause
an automatic second paid provider request.

No worker loop, customer billing or automatic image generation is enabled
by this change.
