# Little Legend Story Writer — integration notes

## Delivered in this change

- `story_writer.write_manuscript` composes personalized chapter jobs from
  the existing approved hero contract, story graph and creative controls.
- Approved chapters are immutable during generation; unfinished chapters
  can be regenerated selectively. Per-chapter callback supports durable
  checkpointing by a future persistence layer.
- `OpenAIChapterWriter` is an injected, opt-in text-only adapter. It is not
  automatically connected to HTTP routes or background workers.
- The model and output budget must be explicitly configured.
- Unit tests use fake providers; no paid AI calls occur in CI.

## Production wiring checklist

1. Validate owner and story ID before loading any draft.
2. Require accepted service terms, approved hero description, explicit
   provider-processing disclosure and an enabled text-generation feature flag.
3. Configure model, budget, timeout, retries, idempotency and rate limits.
4. Persist every completed chapter in the owner's story draft; never mark
   partial work as complete.
5. Allow parental preview, corrections and regeneration of unapproved
   chapters. Approved chapters require explicit unlock.
6. Run a separate semantic editor to check the original child's facts,
   consistent voice, chapter causality, age-appropriateness and agency.
7. Require final parental and editorial approval before publication.

This change intentionally does not activate photo processing or transfer
children's photographs to AI services. Photo-based portrait generation
remains blocked pending a separate consent/security release.
