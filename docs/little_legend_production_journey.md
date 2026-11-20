# Little Legend — Production Journey & Railway services

## Customer progress API

Authenticated, owner-scoped endpoint:

`GET /little-legend/api/order-quotes/{quote_id}/journey`

The router prefix is defined in `app/little_legend/router.py`; confirm the
deployed mount before exposing links to customers. Response fields are
`quote_id`, `stage`, `action`, `writer_completed`, `writer_total`,
`illustrations_completed`, `illustrations_total`,
`payment_verified` and `delivered`.

The API never returns manuscript text, child details, prompts, media URLs,
payment secrets, or object-storage keys. It uses verified payment receipts,
owner-scoped SQL queries, persisted queue statuses, parental approvals, and
Telegram delivery receipts. Responses are marked `Cache-Control: no-store`.

The `action` is a **machine-readable suggestion**, not an automatic approval:
`complete_payment`, `approve_outline`, `approve_text_ai`,
`approve_manuscript`, `approve_image_ai`, `approve_final_book`,
`wait`, `contact_support`, `download_book`.

## Railway service layout

Create **four distinct Railway services** from the same GitHub repository,
all using the same production Neon database:

| Service | Config-as-code path |
| --- | --- |
| AI chapter writer | `railway.little-legend-writer.toml` |
| AI illustration generator | `railway.little-legend-illustration.toml` |
| Paid production conductor | `railway.little-legend-conductor.toml` |
| PDF assembly and Telegram delivery | `railway.little-legend-worker.toml` |

Do not replace the existing bot/web service. Set each worker's Railway
config-as-code path in the service settings; merging the files does **not**
automatically provision Railway services.

Required opt-in flags:

- Writer and illustrator: `LL_AI_PRODUCTION_ENABLED=true`.
- Writer: `LL_WRITER_ENABLED=true`, `LL_TEXT_AI_CONSENT_ENABLED=true`.
- Illustrator: `LL_ILLUSTRATION_ENABLED=true`,
  `LL_IMAGE_AI_CONSENT_ENABLED=true`.
- Conductor: `LL_CONDUCTOR_ENABLED=true`,
  `LL_ILLUSTRATION_PRICE_MICRO_USD` set to a positive integer.

Configure OpenAI keys, provider disclosure fields, S3 private HTTPS credentials,
Neon credentials, Telegram token and per-story budget according to the
existing worker docs. Never commit these secrets. Activate billable workers
only after consent and payment testing.

## Acceptance checklist

1. Verify signed WayForPay webhook and owner-scoped paid quote.
2. Parent approves outline and grants text AI consent; conductor enqueues.
3. Writer produces chapters; API reports progress without story text.
4. Parent reviews and approves manuscript.
5. Parent grants image AI consent; conductor enqueues art.
6. Illustrator saves all images in private S3; verify count and revisions.
7. Parent/editorial final approval; PDF worker assembles and sends.
8. Confirm persisted Telegram message receipt; API reports delivered.
9. Restart each worker during idle and during a controlled test; verify no
   repeated provider dispatch for uncertain outcomes.
10. Test a rejected payment, revoked consent, missing budget and failed AI
    effect; no billable work or premature delivery should occur.

This PR adds status observability and deployable worker configurations;
it does not claim that Railway services are already running or that a
production end-to-end order has passed.
