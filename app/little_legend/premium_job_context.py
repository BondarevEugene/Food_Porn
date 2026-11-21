"""Recover premium art context from durable Neon job payloads.

Only reference identifiers and story directions are stored, never source
photos, API secrets or generated image bytes.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_batch_manifest import PremiumBatchManifest
from app.little_legend.premium_visual_contract import BookVisualPlan


class PremiumJobContext(BaseModel):
    manifest: PremiumBatchManifest
    plan: BookVisualPlan


def restore_premium_job_context(job: IllustrationJob) -> PremiumJobContext:
    """Fail closed on missing, corrupt or cross-owner persisted snapshots."""
    if (not job.premium_manifest_fingerprint
            or not job.premium_story_fingerprint
            or not job.premium_manifest_snapshot
            or not job.premium_plan_snapshot):
        raise PermissionError("Premium job has no durable production context")
    context = PremiumJobContext.model_validate({
        "manifest": job.premium_manifest_snapshot,
        "plan": job.premium_plan_snapshot,
    })
    manifest, plan = context.manifest, context.plan
    if (manifest.owner_id != job.owner_id
            or manifest.story_id != job.story_id
            or manifest.fingerprint != job.premium_manifest_fingerprint
            or manifest.genre != plan.genre.value):
        raise PermissionError("Premium job context identity mismatch")
    matches = [request for request in manifest.requests
               if request.moment_id == job.scene_id]
    if (len(matches) != 1
            or matches[0].expected_revision != job.expected_revision
            or matches[0].estimated_micro_usd
            != round(job.estimated_cost_usd * 1_000_000)):
        raise PermissionError("Premium job slot is stale or inconsistent")
    # Canonical reconstruction detects edits to cover prompts, scene direction,
    # price, genre design and the manifest digest, including after a restart.
    from app.little_legend.premium_batch_manifest import build_premium_batch_manifest

    unit = manifest.requests[0].estimated_micro_usd
    if any(request.estimated_micro_usd != unit for request in manifest.requests):
        raise PermissionError("Premium request prices differ")
    revisions = [
        manifest.requests[index].expected_revision
        for index in range(1, len(manifest.requests), 2)
    ]
    canonical = build_premium_batch_manifest(
        owner_id=job.owner_id, story_id=job.story_id, plan=plan,
        chapter_revisions=revisions,
        image_unit_cost_usd=str(unit / 1_000_000),
        max_budget_usd=str(manifest.max_budget_micro_usd / 1_000_000),
    )
    if (manifest.fingerprint != canonical.fingerprint
            or manifest.requests != canonical.requests
            or manifest.total_estimated_micro_usd
            != canonical.total_estimated_micro_usd):
        raise PermissionError("Premium persisted context was modified")
    return context
