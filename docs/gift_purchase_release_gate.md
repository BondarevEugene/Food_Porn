# Food_Porn · Unified gift purchase release gate

Status: **closed by default**. Never enable unified checkout simply because unit tests or a sandbox callback succeed.

## Runtime configuration

The application stores payment state and delivery checkpoints in PostgreSQL, but photo references and generated JPG/PNG/MP4 files are stored in the filesystem. Configure an actual **persistent Railway volume** and point `STORAGE_ROOT` to its mounted path. `STORAGE_ROOT=storage` on an ephemeral deployment is not sufficient: files disappear at redeploy/restart.

Configure WayForPay production credentials through Railway secret variables. Keep `WAYFORPAY_TEST_MODE=true` for sandbox-only validation; it deliberately cannot trigger billable image/video fulfillment. Configure `WAYFORPAY_VIDEO_STORY_PRICE_UAH` before testing the video or bundle. Confirm that `PUBLIC_BASE_URL` is the stable HTTPS hostname that WayForPay can reach.

`GIFT_UNIFIED_CHECKOUT_ENABLED=false` must remain the production default while validating. Never use production card payment to exercise the new behavior before the persistence and delivery tests succeed.

## Automated verification

GitHub Actions runs unit, lint and database migration checks and a separate `postgres-gift-integration` job with PostgreSQL 16 in an isolated database named `food_porn_test`. That job verifies simultaneous webhook approvals, a single winning entitlement, replay idempotency, and mismatched payment amounts.

The integration test accepts only a loopback-host PostgreSQL database whose exact database name is `food_porn_test`. It creates a random schema and deletes the schema after testing. It does not connect to Neon production.

## Manual end-to-end QA, after deployment configuration

1. Set `STORAGE_ROOT` to a verified mounted volume. Upload photographs, restart the Railway container, and confirm both archived photos and generated assets remain accessible.
2. Use a dedicated tester Telegram account to select **video only**, enter goals and style, and verify the quote includes only the video price. Repeat for **collage only** and **both**; ensure the bundle shows exactly one total.
3. In sandbox, verify HMAC-protected callbacks and order-status handling without generating paid assets. Do not mistake sandbox settlement for a real charge.
4. After a controlled live release is approved, enable `GIFT_UNIFIED_CHECKOUT_ENABLED=true` on a restricted staging instance, complete one low-cost live purchase, and verify exactly one callback grants entitlement. Confirm selected media arrive in Telegram.
5. Trigger a duplicate webhook and repeated **Check payment**. Verify there is one receipt, one source artwork generation, and no duplicate sent files.
6. Restart the bot after an in-progress order and check that the stored record can resume without a second payment. Retry a failed MP4 delivery without repeating an already sent collage.
7. Turn checkout off again if media disappear after restart, payment callbacks are not reliably signed/processed, or repeated payments unexpectedly change entitlement.

## Known limitations

- GitHub-hosted Postgres tests do not validate your actual Railway persistent-volume mount, public HTTPS webhook, Telegram message delivery, image service quota, or a real WayForPay settlement.
- The immediate post-webhook generation currently runs as a process-bound response background task; while checkpoints allow manual resumption via **Check payment**, an always-on restart-safe job dispatcher/worker is recommended before scale-out.
- Telegram delivery attempts are checkpointed per product; a network interruption after Telegram accepts a file but before the database checkpoint is committed can still cause a duplicate on retry. Exactly-once cross-service delivery requires reconciliation support.
- Keep user images private. Restrict backup, storage and logs access; determine retention/deletion policy before public rollout.
