# Little Legend: production AI queue workers

This release connects the existing **writer** and **illustration** queue processors
to independently deployable polling services. It does **not** create or approve
stories automatically: parent consent, outline approval, chapter approval,
image consent, budgets and editorial review remain enforced by the existing
queue processors.

## Railway setup

Create two separate Railway services from the same repository, with the same
Neon database, using the following start commands:

- Writer: `python -m app.little_legend.ai_production_runner --mode writer`
- Illustration: `python -m app.little_legend.ai_production_runner --mode illustration`

Keep the existing bot/web and PDF delivery worker services separate. Run only
one instance of each AI service initially; queue claims use database locks.

Enable each service **only after** the parent-facing disclosure and provider
settings are verified. Set `LL_AI_PRODUCTION_ENABLED=true` explicitly.

Writer also requires `LL_WRITER_ENABLED=true`, `OPENAI_API_KEY`, and
`LL_TEXT_AI_CONSENT_ENABLED=true`, plus the complete text disclosure variables
used by `configured_text_ai_disclosure()`.

Illustration also requires `LL_ILLUSTRATION_ENABLED=true`,
`LL_IMAGE_AI_CONSENT_ENABLED=true`, `OPENAI_API_KEY`,
`LL_ILLUSTRATION_PRICE_MICRO_USD` and the five
`LITTLE_LEGEND_ART_S3_*` credentials. The S3 endpoint must be HTTPS.
Complete the image disclosure variables used by
`configured_image_ai_disclosure()`.

All AI effects remain protected by the existing transactional queue claim,
consent checks, provider-dispatch fence, budget reservations and receipt
handling. Ambiguous provider calls must be manually reconciled; never
force-reset a dispatched job to queued.

## Acceptance

1. Apply Alembic migrations on Neon and confirm budget provisioning.
2. Queue an approved outline with valid text AI consent.
3. Start writer service and verify chapter results are persisted.
4. Parent approves manuscript and enables image AI consent.
5. Queue illustrations; start illustration service; verify private art assets.
6. Parent/editorial approves all materials; existing paid-book release worker
   assembles PDF and delivers it to Telegram with receipt.
7. Simulate service restart; verify no duplicate provider dispatch or Telegram
   send and inspect uncertain effects before operator action.

`--once` is available for a single controlled queue cycle. This deployment
does not automatically enqueue new story jobs or bypass parent review.
