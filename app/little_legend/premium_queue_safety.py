"""Validate a premium illustration manifest against the live approved story.

Used before transactional queue insertion and again before paid dispatch.
No image provider calls, storage reads, or database writes occur here.
"""
from __future__ import annotations

import hashlib
import json

from app.little_legend.premium_batch_manifest import PremiumBatchManifest
from app.little_legend.premium_visual_contract import BookVisualPlan
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


def premium_story_fingerprint(
    *, graph: StoryGraph, manuscript: StoryManuscript,
) -> str:
    """Fingerprint all approved story content, not just revision numbers."""
    payload = {
        "graph": graph.model_dump(mode="json"),
        "manuscript": manuscript.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def require_premium_batch_ready(
    *, manifest: PremiumBatchManifest, plan: BookVisualPlan,
    graph: StoryGraph, manuscript: StoryManuscript,
    owner_id: int, story_id: int,
) -> str:
    """Fail closed on stale, misordered or misattributed premium art requests.

    Returns a content fingerprint for subsequent dispatch-fence comparison.
    """
    if owner_id <= 0 or story_id <= 0 or (
        manifest.owner_id != owner_id or manifest.story_id != story_id
    ):
        raise PermissionError("Premium batch belongs to another owner or story")
    nodes = sorted(graph.nodes, key=lambda node: node.order)
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if not nodes or len(chapters) != len(manuscript.chapters) or (
        set(chapters) != {node.id for node in nodes}
    ):
        raise PermissionError("Premium story chapters are incomplete")
    if not manuscript.parent_approved or any(
        not chapter.approved for chapter in chapters.values()
    ):
        raise PermissionError("Premium manuscript is not approved")
    if len(plan.illustrations) != 2 * len(nodes) or (
        len(manifest.requests) != len(plan.illustrations) + 1
    ):
        raise PermissionError("Premium visual plan is incomplete")
    if manifest.genre != plan.genre.value:
        raise PermissionError("Premium genre has changed")
    cover = manifest.requests[0]
    if (cover.moment_id != "premium-cover" or cover.chapter_index != 0
            or cover.reference_id != plan.cover_reference_id
            or cover.expected_revision != max(
                chapter.revision for chapter in chapters.values()
            )):
        raise PermissionError("Personalized cover request is stale")
    for index, slot in enumerate(plan.illustrations):
        node = nodes[index // 2]
        request = manifest.requests[index + 1]
        if (slot.chapter_index != node.order
                or request.moment_id != slot.moment_id
                or request.chapter_index != slot.chapter_index
                or request.reference_id != slot.source_reference_id
                or request.scene_description != slot.scene_description
                or request.costume_direction != slot.costume_direction
                or request.background_direction != slot.background_direction
                or request.expected_revision != chapters[node.id].revision):
            raise PermissionError("Premium illustration moment is stale or mismatched")
    if any(
        not request.requires_identity_review or not request.requires_face_safe_margin
        for request in manifest.requests
    ):
        raise PermissionError("Premium identity and crop review are mandatory")
    return premium_story_fingerprint(graph=graph, manuscript=manuscript)
