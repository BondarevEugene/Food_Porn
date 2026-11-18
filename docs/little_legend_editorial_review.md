# Little Legend — human editorial review

The manuscript remains a draft until a reviewer explicitly confirms
character fidelity, age suitability, continuity and final parental approval.

The editorial review API is owner-scoped:
- GET /little-legend/api/stories/{story_id}/editorial-review
- PUT /little-legend/api/stories/{story_id}/editorial-review

A successful preflight permits **print proof preparation only**, never
automatic publication. Literal hero-name matching is only a conservative
signal; it is not semantic identity verification.

Every chapter edit, unlock or approval change resets the review decision.
The generic story editor cannot change the review decision and cannot
rename the hero after a manuscript exists.

Children's photos and image generation remain disabled.
