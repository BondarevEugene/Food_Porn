# Little Legend — story from the parent's sketches

The parent supplies a premise, ordered story moments, the hero's wish,
challenge, decisive choice, ending, important relationships, and topics
to avoid. The parent may submit only the premise and one story moment;
missing creative details are returned as questions rather than invented
facts about a real child.

**Preview:** `POST /little-legend/api/stories/{id}/sketch/preview`
**Save:** `PUT /little-legend/api/stories/{id}/sketch`

Both routes require existing owner authentication. Optional
`chapter_count` query parameter accepts 3–12. Preview never writes.
Save atomically persists the original source sketch, story graph and
narrative arc in the story JSON. Saving is blocked once written chapters
or writer receipts exist, preventing silent loss of paid or approved work.

This is a **deterministic story outline**, not an AI-written book.
The source moments are preserved in their original order and empty beats
remain editorial questions. The writer integration must explicitly use
the original parent sketch, honor avoid-list and emotional safety notes,
and obtain provider-processing consent before sending children's details
to a third-party AI service. Uploaded child photographs remain disabled.

Next MVP step: connect the approved sketch, hero contract, writing plan,
provider and transactional queue to a user-triggered text-generation flow.
Then illustrate, typeset a final book, collect payment and deliver.
