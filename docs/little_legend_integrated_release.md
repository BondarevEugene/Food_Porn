# Little Legend — integrated release acceptance

## New customer path

In the Telegram product menu, open **My books**, choose an owned story and
press **Prepare book**. The action assembles only existing approved manuscript
and completed approved illustrations. It does not start paid AI work.

If the approved PDF is successfully assembled and sealed into private storage,
the same chat displays **Get PDF**. Sending remains protected by the durable
Telegram effect ledger; uncertain deliveries must be reconciled by support
rather than automatically retried.

The book preparation action is owner-scoped and private-chat-only. If approval,
illustration revision or S3 configuration is incomplete, it fails closed.

## Required environment

Configure the five existing `LITTLE_LEGEND_S3_*` variables in Railway:
`ENDPOINT_URL`, `BUCKET`, `REGION`, `ACCESS_KEY_ID`,
`SECRET_ACCESS_KEY`. The generated-art and sealed-PDF stores use distinct
private prefixes in the configured bucket. No public ACLs or URLs are used.

## Offline acceptance

For a test PDF already on the operator's local disk:

```powershell
python -m app.little_legend.pdf_acceptance_cli .\book.pdf --minimum-pages 15
```

The command emits a privacy-preserving JSON report and returns exit code 0
only when the PDF passes digital structural acceptance. It does **not** emit
the child's name, manuscript, illustrations or PDF content. Page count 15 is
an example, not a universal guarantee for a 12-scene book.

## Manual staging gate

1. Use a test account with explicitly approved manuscript and illustrations.
2. Confirm the art and PDF prefixes are private in S3.
3. Open the story from Telegram and prepare it once.
4. Confirm the sealed manifest exists in Neon and the PDF is retrievable.
5. Send to the owner in a private chat and confirm the message ID.
6. Simulate an ambiguous Telegram failure and check the CRM reconciliation
   queue. Never force a second send without verification.
7. Check Cyrillic, page flow, image placement and child likeness by viewing
   the PDF; automated checks cannot guarantee aesthetic quality.

This release targets a **digital editorial book**, not a press-certified
physical print. CMYK, bleed, PDF/X and printer proof are separate gates.
