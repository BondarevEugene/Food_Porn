# Little Legend — Railway production acceptance from a smartphone

This release adds a **zero-network deployment preflight** and integration
tests that exercise the same book across the conductor, customer progress
view, release readiness and PDF worker. It does **not** create Railway
services, charge a card, call OpenAI or send a Telegram message.

## CI and local smoke

The standard GitHub `lint-and-test` job runs
`tests/test_little_legend_deployment_preflight.py` and
`tests/test_little_legend_production_acceptance.py` alongside the other
tests. The Railway configuration contract can also be checked with:

```bash
python -m app.little_legend.deployment_preflight
```

This command checks all four config-as-code files and restart policies,
without needing any secrets. It is safe to run in GitHub Actions.

## Railway setup (phone browser)

Create **four separate services** from the same GitHub repository, leaving
the existing web/bot service intact. For each service set its
**Config File Path** in Railway settings:

| Railway service | Config file | Safe preflight |
| --- | --- | --- |
| Production conductor | `railway.little-legend-conductor.toml` | `--service conductor` |
| Chapter writer | `railway.little-legend-writer.toml` | `--service writer` |
| Illustration worker | `railway.little-legend-illustration.toml` | `--service illustration` |
| PDF + Telegram worker | `railway.little-legend-worker.toml` | `--service pdf` |

For each service, provision the required environment variables in the
Railway Variables screen. Do **not** copy production secrets into GitHub,
screenshots, chat or CI logs. After setting variables, use Railway's
terminal (where available) to run:

```bash
python -m app.little_legend.deployment_preflight --service conductor --check-env
```

Replace `conductor` with `writer`, `illustration` or `pdf` for the
corresponding service. Only missing variable **names** and invalid
configuration categories are printed; values are never logged.

These opt-in flags are deliberately absent by default:

- Conductor: `LL_CONDUCTOR_ENABLED=true`
- Writer: `LL_AI_PRODUCTION_ENABLED=true`,
  `LL_WRITER_ENABLED=true`, `LL_TEXT_AI_CONSENT_ENABLED=true`
- Illustration: `LL_AI_PRODUCTION_ENABLED=true`,
  `LL_ILLUSTRATION_ENABLED=true`, `LL_IMAGE_AI_CONSENT_ENABLED=true`

The PDF worker additionally needs the Telegram bot token and both
private S3 credential sets. All services use the same Neon PostgreSQL
database. Do not enable billable workers until the legal disclosure,
consent, verified payment and per-book budget are configured.

## Controlled end-to-end acceptance

1. Use one dedicated test account and test quote; verify signed payment.
2. Approve outline and explicit text-AI disclosure, then run conductor.
3. Verify the writer produces each chapter only once.
4. Approve every chapter and the complete manuscript.
5. Grant image-AI disclosure, then verify each scene has one illustration.
6. Check `GET /little-legend/api/order-quotes/{quote_id}/release-readiness`.
   `release_ready` must be `true` only after editorial/parent approval.
7. Let the PDF worker assemble a private PDF and deliver it to Telegram.
8. Verify the stored Telegram message ID and `journey` stage `delivered`.
9. Restart each worker **while idle**; verify no duplicate work is created.
10. In a dedicated non-billable test, simulate missing payment, revoked
    final approval, stale art revision and ambiguous delivery. Each must
    block automatic release or resend.

**Do not force a live crash between external provider dispatch and receipt**
without an isolated test environment and operator reconciliation. Provider
outcomes can be ambiguous and potentially billable.

## Limitations

The CI acceptance suite is deterministic and provider-free. Passing CI is
not proof that live Railway services, Neon migrations, S3 buckets, Telegram
delivery and payment credentials are correctly provisioned. Production
readiness requires a supervised live test order and recorded receipts.
