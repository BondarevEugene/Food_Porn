# Little Legend — Hero-first narrative contract

## Product rule

The protagonist must be the exact child described by the customer, not a
generic fantasy hero. The system must not invent real-world biographical
facts about the child. A fantasy plot is fictional; the child's original
name, age, appearance, habits, phrases and relationships are authoritative.

## Story creation

1. Capture the parent's description and allow edits before generation.
2. Extract a canonical HeroContract from the saved BookBlueprint.
3. Merge legacy story fields `habits` and `phrases` only when the richer
   profile has no corresponding information.
4. Supply the same immutable facts and continuity instructions to every
   scene. Use important facts naturally through actions and dialogue.
5. Make the hero solve the central problem; side characters can support.
6. Check each scene for omissions, contradictions, voice, relationships,
   emotional appropriateness and continuity.
7. Return questionable passages for editing and parental approval.

The endpoint `GET /little-legend/api/stories/{story_id}/hero-contract`
returns a structured brief, per-scene directives and a conservative audit.
It uses existing owner authentication. It does not send content to AI,
create a manuscript or change the database.

## Simple / director modes

Simple mode should show the parent's own description and a small editable
summary. Director mode can expose every fact, immutable/important priorities,
scene-by-scene continuity and human review. The current PR implements the
shared backend contract; the editing UI and AI writer remain separate work.

## Critical limitations

Literal name checks are insufficient for Ukrainian/Russian grammatical
inflections, pronouns and synonyms. They cannot verify personality,
semantic contradictions or that the hero has agency. The audit explicitly
never claims fidelity or publication readiness. Future generation must
add semantic checks, per-scene evidence and a final editorial gate.
No child photos are required for text-only personalization.
