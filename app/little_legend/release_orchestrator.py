"""Connect real approved story production to sealed private PDF and Telegram.

The release is persisted before dispatch. Telegram effects are durably fenced
by dispatch_release_pdf; uncertain outcomes must never be retried automatically.
"""
from __future__ import annotations

from app.little_legend.book_delivery import BookDelivery, DeliveryStatus
from app.little_legend.book_release import BookRelease
from app.little_legend.owned_production import load_owned_production
from app.little_legend.private_pdf_store import (
    PrivatePDFStore,
    persist_release_pdf,
    restore_release_pdf,
)
from app.little_legend.release_manifest_store import (
    ReleaseManifest,
    get_release_manifest,
    mark_release_delivery,
    register_release,
)
from app.little_legend.telegram_pdf_dispatch import PDFSender, dispatch_release_pdf


async def prepare_owned_release(
    *, owner_id: int, story_id: int, art_store,
    pdf_store: PrivatePDFStore,
) -> ReleaseManifest:
    """Assemble once from approved art, persist private PDF, register in Neon."""
    existing = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if existing is not None:
        return existing
    production = await load_owned_production(owner_id=owner_id, story_id=story_id)
    package = production.assemble(store=art_store)
    persist_release_pdf(
        store=pdf_store, package=package,
        owner_id=owner_id, story_id=story_id,
    )
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
