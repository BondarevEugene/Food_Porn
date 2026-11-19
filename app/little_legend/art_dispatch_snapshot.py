"""Deterministic fingerprint of the exact art context used by a worker.

This prevents a stale in-memory prompt from being dispatched after a parent
edits a story while the worker is waiting for the transactional fence.
"""
from __future__ import annotations

import hashlib
import json

from app.little_legend.router import StoryDraft


def art_dispatch_fingerprint(draft: StoryDraft, scene_id: str) -> str:
    from app.little_legend.illustration_runner import directed_scene_for_provider
    from app.little_legend.reviewed_identity_prompt import reviewed_identity_continuity

    if draft.graph is None or draft.manuscript is None:
        raise PermissionError("Art source is unavailable")
    scene = next((item for item in draft.graph.nodes if item.id == scene_id), None)
    chapter = next(
        (item for item in draft.manuscript.chapters if item.scene_id == scene_id), None
    )
    if scene is None or chapter is None:
        raise PermissionError("Art scene or chapter is unavailable")
    payload = {
        "scene": directed_scene_for_provider(scene).summary,
        "hero": draft.hero,
        "style": (
            draft.blueprint.controls.illustration_style
            if draft.blueprint else "storybook"
        ),
        "continuity": reviewed_identity_continuity(
            blueprint=draft.blueprint, bible=draft.identity_bible,
            hero_name=draft.hero,
        ),
        "chapter_revision": chapter.revision,
        "chapter_approved": chapter.approved,
        "manuscript_approved": draft.manuscript.parent_approved,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
