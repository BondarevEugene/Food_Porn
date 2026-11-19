# Little Legend flagship commerce — stage 1

The two **editions** are a digital illustrated PDF and a physical printed
book. These are variants of the Little Legend story product, not the existing
Food_Porn menu/collage products.

## Admin-configured prices

Set `LITTLE_LEGEND_DIGITAL_PRICE_KOP` and
`LITTLE_LEGEND_PRINT_PRICE_KOP` in Railway. Values are positive **integer
kopecks** (e.g. 129900 means 1299.00 UAH). No prices are invented or
silently defaulted. Invalid settings fail closed. The Telegram product screen
offers **Editions & prices** and the HTTP catalog is at
`GET /little-legend/api/catalog`.

This is an informational catalog, **not an enabled checkout**. The digital
edition can be quoted when configured, but payment initiation and verified
payment receipts must be implemented before commercial orders. Print is
intentionally unavailable until press-ready export, fulfillment and shipping
are validated. A configured print price is displayed only as a prospective
price; it does not unlock purchasing.

## Required before commercial launch

- Owner-only CRM tariff editor, audit and effective dates, without storing
  prices as floats
- Server-side immutable order quote, payment intent, provider callback
  verification, idempotent payment receipt and refund handling
- Payment-confirmed production gate; do not start paid AI jobs on a client
  redirect alone
- Real premium visual book redesign, customer review of proof and print proof
- Print supplier, bleed, CMYK/PDF-X, delivery regions and shipping policy
- End-to-end staging test with Railway, Neon, S3, Telegram and provider sandbox

Never advertise this stage as payment-ready or press-certified.
