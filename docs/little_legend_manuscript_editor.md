# Little Legend — persistent manuscript editor

The StoryDraft now stores an optional StoryManuscript in its existing
owner-scoped JSON record in Neon PostgreSQL. No migration is required.

## API

- GET /little-legend/api/stories/{story_id}/manuscript
- POST /little-legend/api/stories/{story_id}/manuscript/{scene_id}/draft
- PUT /little-legend/api/stories/{story_id}/manuscript/{scene_id}
- POST /little-legend/api/stories/{story_id}/manuscript/{scene_id}/approval

All routes require the existing authenticated owner. Every mutation uses a
database row lock, and updates the story JSON in a single transaction.
Existing generic story editor PUT calls preserve the manuscript if omitted,
and reject direct replacement attempts.

Approved chapters cannot be overwritten until explicitly unlocked.
Editing increments the revision and invalidates overall parent approval.
No endpoint in this PR calls an external AI model.

## Next step

Connect the opt-in Story Writer to a durable job queue. Save each generated
chapter with a monotonic revision, implement retry-safe idempotency and
optimistic concurrency checks for interactive editors. Add semantic
identity review and final parent approval before print.
