# Little Legend — writer checkpoints

An internal trusted worker can persist a generated chapter with
`persist_writer_checkpoint(story_id, owner_id, checkpoint)`.

The operation locks the owner-scoped story row in Neon PostgreSQL and
atomically saves:
- chapter text and incremented revision;
- the last committed writer job ID for that scene;
- invalidation of editorial approval.

The same job ID is a safe replay. A stale revision, unknown scene, different
owner or approved chapter cannot be overwritten.

This PR does **not** add an HTTP endpoint for job receipts. A public endpoint
would allow clients to impersonate the trusted writer. AI execution, job
ownership verification, queue, provider consent and retry orchestration are
separate release gates. The job-ID receipt is scoped to a scene, not a full
job-history audit log. Never put raw child photographs in writer payloads.
