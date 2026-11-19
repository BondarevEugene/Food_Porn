# Little Legend: sealed release package

`build_release_package` is a pure orchestration boundary for the existing
approved-manuscript, private-art, A5 editorial PDF and immutable-release layers.

It rejects missing editorial approval and foreign illustration jobs **before**
accessing private storage. Existing assembly verifies that all scene jobs are
completed, owner-scoped, approved and revision-matched. The package binds
the PDF SHA-256 to the release and a fresh READY delivery state. Consumers
must call `verified_pdf(owner_id=..., story_id=...)` before using the bytes.

This does **not** persist a release or deliver it to Telegram. The application
must durably persist the release and the SENDING state before a Telegram send,
then persist SENT only after acknowledgement; uncertain responses must not
trigger automatic resends. A database-backed orchestration and a real
end-to-end delivery test are still required before claiming live fulfillment.

The rendered PDF remains an editorial proof, not a print-ready product.
