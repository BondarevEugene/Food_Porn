"""Connect real approved story production to sealed private PDF and Telegram.

The release is persisted before dispatch. Telegram effects are durably fenced
by dispatch_release_pdf; uncertain outcomes must never be retried automatically.
"""
from __future__ import annotations

import asyncio

from app.little_legend.book_delivery import BookDelivery, DeliveryStatus
from app.little_legend.book_release import BookRelease
from app.little_legend.owned_production import load_owned_production
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    get_effect,
    request_fingerprint,
)
from app.little_legend.private_pdf_store import (
    PrivatePDFStore,
    pdf_object_key,
    persist_release_pdf,
    restore_release_pdf,
    validate_pdf,
)
from app.little_legend.registered_artifact_writes import register_release_pdf
from app.little_legend.release_manifest_store import (
    ReleaseManifest,
    get_release_manifest,
    mark_release_delivery,
    register_release,
)
from app.little_legend.telegram_pdf_dispatch import (
    PDFSender,
    dispatch_release_pdf,
    pdf_delivery_effect_key,
)


async def prepare_owned_release(
    *, owner_id: int, story_id: int, art_store,
    pdf_store: PrivatePDFStore,
    registry_bucket: str | None = None,
) -> ReleaseManifest:
    """Assemble once from approved art, persist private PDF, register in Neon."""
    existing = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if existing is not None:
        return existing
    production = await load_owned_production(owner_id=owner_id, story_id=story_id)
    package = production.assemble(store=art_store)
    if registry_bucket is not None:
        pdf = package.verified_pdf(owner_id=owner_id, story_id=story_id)
        await register_release_pdf(
            store=pdf_store, bucket=registry_bucket,
            owner_id=owner_id, story_id=story_id,
            pdf=pdf, pdf_sha256=package.release.pdf_sha256,
        )
    else:
        persist_release_pdf(
            store=pdf_store, package=package,
            owner_id=owner_id, story_id=story_id,
        )
    # Never advertise a ready PDF before the private store can read back
    # the exact sealed bytes. A failed read leaves no delivery manifest.
    stored_pdf = await asyncio.to_thread(
        pdf_store.get,
        key=pdf_object_key(
            owner_id=owner_id, story_id=story_id,
            pdf_sha256=package.release.pdf_sha256,
        ),
    )
    validate_pdf(stored_pdf, expected_sha256=package.release.pdf_sha256)
    return await register_release(
        package=package, owner_id=owner_id, story_id=story_id,
    )


async def send_owned_release(
    *, owner_id: int, story_id: int, pdf_store: PrivatePDFStore,
    sender: PDFSender,
) -> ReleaseManifest:
    """Send a previously sealed release, never assemble or call AI here.

    The effect ledger is the authority. Even if updating the manifest fails,
    a repeated send remains fenced by the effect ledger.
    """
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None:
        raise PermissionError("Release is not prepared")
    if manifest.status != DeliveryStatus.READY:
        raise PermissionError("Release delivery already started or completed")
    release = BookRelease(
        owner_id=owner_id, story_id=story_id,
        revision_fingerprint=manifest.revision_fingerprint,
        pdf_sha256=manifest.pdf_sha256, scene_count=manifest.scene_count,
    )
    delivery = BookDelivery(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=manifest.pdf_sha256,
    )
    package = restore_release_pdf(
        store=pdf_store, release=release, delivery=delivery,
        owner_id=owner_id, story_id=story_id,
    )
    outcome = await dispatch_release_pdf(
        package=package, owner_id=owner_id, story_id=story_id,
        sender=sender,
    )
    return await mark_release_delivery(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=manifest.pdf_sha256,
        status=outcome.status,
        message_id=outcome.telegram_message_id,
    )


async def reconcile_owned_delivery(
    *, owner_id: int, story_id: int,
) -> ReleaseManifest:
    """Repair manifest projection from a confirmed durable Telegram effect.

    Never calls Telegram, retries delivery or changes an uncertain effect.
    An unresolved/ambiguous attempt is left for explicit operator review.
    """
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None:
        raise PermissionError("Release is not prepared")
    if manifest.status == DeliveryStatus.SENT:
        return manifest
    effect = await get_effect(
        effect_key=pdf_delivery_effect_key(
            owner_id=owner_id, story_id=story_id,
            pdf_sha256=manifest.pdf_sha256,
        ),
        owner_id=owner_id, story_id=story_id,
        kind=EffectKind.TELEGRAM_PDF,
        request_sha256=request_fingerprint({
            "owner_id": owner_id, "story_id": story_id,
            "pdf_sha256": manifest.pdf_sha256,
            "destination": owner_id,
        }),
    )
    if effect is None:
        return manifest
    if effect.status == EffectStatus.CONFIRMED:
        reference = effect.provider_reference
        if reference is None or not reference.isdecimal() or int(reference) <= 0:
            raise ValueError("Confirmed effect lacks a valid Telegram message ID")
        return await mark_release_delivery(
            owner_id=owner_id, story_id=story_id,
            pdf_sha256=manifest.pdf_sha256,
            status=DeliveryStatus.SENT, message_id=int(reference),
        )
    if effect.status == EffectStatus.UNCERTAIN and manifest.status == DeliveryStatus.READY:
        return await mark_release_delivery(
            owner_id=owner_id, story_id=story_id,
            pdf_sha256=manifest.pdf_sha256,
            status=DeliveryStatus.UNCERTAIN,
        )
    # RESERVED or DISPATCHED can still be in flight: never project or resend.
    return manifest
