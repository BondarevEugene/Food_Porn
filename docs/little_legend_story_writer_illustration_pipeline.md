# Little Legend — Story Writer and Illustration Studio delivery contract

## Non-negotiable product behavior

The child described during onboarding is the protagonist of every chapter.
Their name, age, relationships, appearance, mannerisms, interests and favorite
phrases must remain stable. Narrative decisions must follow their personality.
Side characters may help but must not replace the child in the climax.

### Text pipeline

1. Capture and confirm the original hero profile.
2. Build immutable/important facts from the parent's own words.
3. Plan the story and individual chapters with shared facts and neighboring
   scene context.
4. Generate manuscript prose in the selected language and reading level.
5. Run semantic checks for identity contradictions, ungrounded biographical
   claims, causality, agency, age-appropriateness and repeated formulaic text.
6. Allow parent edits and chapter-specific regeneration, preserving approved
   chapters and immutable hero facts.
7. Require editorial and parental approval before final publication.

Current implementation covers steps 1-3 as structured data and conservative
gates. It does not yet call an LLM or produce a finished manuscript.

### Illustration pipeline

1. Parent confirms a descriptive identity bible and style.
2. After separate, valid consent and security review, ingest a reference photo
   through the private sanitized-image pipeline.
3. Generate a single reference portrait and obtain explicit parent approval.
4. Use the approved reference and identical fixed visual anchors for each scene.
5. Validate face, hair, eyes, age, distinctive features and consistency;
   flag any drift and regenerate only affected illustrations.
6. Obtain per-scene parental approval and assemble print proofs.

Current implementation provides per-scene specs and a review gate only.
Reference photo processing and photo-based generation remain disabled.
No generative image model can guarantee a pixel-exact copy or perfect
biometric likeness; avoid promising certainty. A recognizable, approved
artistic likeness is the product target.

### Safety

- No child photo bytes, URLs, face vectors or embeddings in story JSON.
- No third-party transfer until processors, contracts, data location and
  parental consent are finalized.
- No child image use for advertising or model training without separate
  authorization.
- Withdrawal must queue media erasure; confirm actual object deletion before
  claiming completion.
- Simple and director modes must share the same identity constraints.
