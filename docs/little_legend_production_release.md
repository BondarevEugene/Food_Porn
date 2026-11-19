# Little Legend — Production & Delivery

## Deployment

This release requires migration `20261119_0026` after `0025`.
Start **one dedicated Railway worker** using:

```powershell
python -m app.little_legend.paid_book_worker
```

The worker does not run inside the web process. Configure the same Neon
`DATABASE_URL`, Telegram `BOT_TOKEN` / application bot configuration,
and the existing generated-illustration S3 credentials:

- `LITTLE_LEGEND_ART_S3_ENDPOINT`
- `LITTLE_LEGEND_ART_S3_BUCKET`
- `LITTLE_LEGEND_ART_S3_REGION`
- `LITTLE_LEGEND_ART_S3_ACCESS_KEY`
- `LITTLE_LEGEND_ART_S3_SECRET_KEY`

Add separate **private** finished-book storage:

- `LITTLE_LEGEND_S3_ENDPOINT`
- `LITTLE_LEGEND_S3_BUCKET`
- `LITTLE_LEGEND_S3_REGION`
- `LITTLE_LEGEND_S3_ACCESS_KEY_ID`
- `LITTLE_LEGEND_S3_SECRET_ACCESS_KEY`

The bucket must have no public access.

## Production contract

1. A verified real WayForPay approval creates one fulfillment job.
2. Worker claims a job in Neon before any external effects.
3. Approved manuscript and revision-matched, completed illustrations are
   mandatory. The existing structural PDF quality check runs.
4. PDF is stored in private S3 under a deterministic owner-scoped key.
5. Only after durable storage does the worker claim Telegram delivery.
6. Re-download is available at
   `GET /little-legend/api/order-quotes/{quote_id}/book.pdf`
   with Telegram Mini App authorization and verified entitlement.

## Operational safeguards

- **Do not** automatically retry a `processing` job after a Railway crash:
  reconcile its stored PDF first.
- **Do not** automatically retry Telegram delivery after
  `delivery_started_at`: the message may have reached the customer.
- `blocked` means the production preconditions or storage need manual
  review; do not mark it paid or ready manually.
- A paid order with missing approved art will be blocked until assets are
  approved; an operator must explicitly requeue after verifying the story.
- This is a **digital editorial PDF**, not a press-certified print edition.
- Validate Telegram file-size limits and S3 credentials in staging before
  enabling production traffic.

## Release checks

Run `ruff check .`, `pytest -q`, and `alembic upgrade head` against a
throwaway PostgreSQL database. Test signed real/sandbox callbacks, duplicate
callbacks, private download ownership, Railway restart between S3 upload
and Telegram delivery, and a deliberately incomplete manuscript.
