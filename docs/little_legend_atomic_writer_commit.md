# Little Legend — atomic writer completion

The trusted worker must use `commit_writer_result` to complete a generated
chapter. It locks the queue row first and the story row second in one Neon
transaction, verifies the current lease token, expiry, job ID, scene and
expected revision, then saves the chapter, job receipt, editorial reset and
completed queue status atomically.

An expired or replaced lease cannot commit. A parent-approved chapter
cannot be overwritten. The function is internal only; no public HTTP
endpoint is added.

**Production integration still required:** a worker loop, explicit
provider-data consent and per-order spending enforcement. Do not wire the
older `persist_writer_checkpoint` helper to an AI worker because that
helper does not validate queue leases. Child-photo processing stays disabled.

Next product-first step: connect the text writer to a user-visible
story-generation action and manuscript progress, then illustrations,
final PDF, payment and delivery.
