# Little Legend release orchestration

The service in `app/little_legend/release_orchestrator.py` links the real,
owner-scoped story and illustration records to private PDF storage, the Neon
release manifest and the already-fenced Telegram delivery ledger.

- `prepare_owned_release`: reuse an existing manifest, otherwise load the
  approved manuscript and completed art jobs, assemble an editorial PDF proof,
  store it privately, and register immutable release metadata.
- `send_owned_release`: require a sealed manifest, read and hash-check the
  private PDF, dispatch through the Telegram effect ledger, then project the
  outcome into the manifest. This function never triggers AI generation.
- A Telegram timeout may mean the document was accepted. The ledger prevents
  automatic re-send; a human must reconcile an uncertain effect.
- A crash after ledger confirmation but before updating the manifest leaves
  the manifest showing READY. This is intentional fail-closed behavior: the
  ledger still fences the repeated send. A reconciliation workflow is needed.

**Not yet a complete customer journey:** these functions are not wired to a
Telegram callback or deployment configuration, and the generated PDF is an
editorial proof, not a print-ready final book. Do not expose a delivery button
until consent, customer authorization, and deployment storage configuration
are validated.
