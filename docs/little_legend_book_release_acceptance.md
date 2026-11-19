# Little Legend — release acceptance and print-production boundaries

## Shipped in this release

- A5 illustrated **editorial proof**, including cover treatment, dedication,
  chapter illustrations, complete approved prose, folios and an editorial endnote.
- Release assembly checks a real PDF before sealing and private S3 persistence.
- Quality report checks page structure, dimensions, missing art, illustration
  effective DPI at the current artwork box, and proof-only markings.
- Telegram delivery is fenced by the persistent effect ledger; uncertain
  outcomes require human reconciliation, never automatic resend.
- All diagnostics use stable codes and dimensions; no children's manuscript,
  portrait, or PDF content is stored in the report.

## Digital delivery acceptance

1. Parent-approved manuscript and every chapter must match the scene graph.
2. Each illustration must be completed, owner-scoped and revision-matched.
3. Renderer must produce a valid A5 PDF with a cover, dedication, all scenes
   and editorial endnote.
4. PDF bytes are SHA256-sealed before private object persistence.
5. Delivery may start only from a READY manifest and must not bypass the
   durable effect ledger.
6. A failure after Telegram dispatch is investigated in the CRM recovery
   queue; never send the same release again without provider reconciliation.

## Not yet certified for commercial print

A successful digital preflight **does not** mean press-ready. The current
proof has no certified 3 mm bleed, PDF/X output intent, CMYK profile, embedded
font audit, imposition, binding/spine calculations or printer-specific
production acceptance. The `print_ready` field therefore remains false.

Effective DPI is an advisory estimate based on the maximum illustrated box
(325 × 260 pt); it is not a substitute for reviewing each placed image,
color profile, sharpness, face safety and printer proof.

## Release verification

- Run `ruff check app/little_legend app/bot/handlers/little_legend.py tests/test_little_legend_book_quality.py`.
- Run `pytest -q tests/test_little_legend_book_quality.py tests/test_little_legend_illustrated_pdf.py tests/test_little_legend_stored_book_proof.py tests/test_little_legend_release_orchestrator.py tests/test_little_legend_telegram_delivery_safety.py`.
- Run the full CI suite and migration smoke.
- In staging, use a consenting test account, an approved test book, configured
  private S3 and Telegram. Verify the generated PDF and the confirmed
  message ID. Test timeout reconciliation separately without replaying.
- Inspect a physical printer proof and secure a printer's written
  specifications before enabling any `print_ready` designation.

## Deployment configuration

Existing Little Legend S3 settings remain mandatory for private delivery.
No new secrets or database migrations are required by this release.
