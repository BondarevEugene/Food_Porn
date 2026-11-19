"""Fail-closed operator audit for Little Legend photo launch readiness.

This audit reports capabilities; it never enables upload or AI processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.privacy_lifecycle import (
    PrivacyLaunchConfig,
    photo_launch_preflight,
)
from app.little_legend.secure_vault import AssetState, upload_capability
from app.little_legend.vault_registry import vault_assets


@dataclass(frozen=True)
class PrivateVaultAudit:
    checked_at: str
    by_state: dict[str, int]
    expired_not_deleted: int
    exhausted_retries: int
    pending_over_24h: int
    requires_operator_attention: bool
    photo_upload_enabled: bool
    photo_processing_enabled: bool
    automatic_deletion_enabled: bool
    launch_blockers: tuple[str, ...]


async def audit_private_vault(
    session: AsyncSession, *, config: PrivacyLaunchConfig,
    now: datetime | None = None,
) -> PrivateVaultAudit:
    """Return aggregate-only diagnostics: never expose child or object identifiers."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    rows = (await session.execute(
        select(vault_assets.c.state, func.count())
        .group_by(vault_assets.c.state)
    )).all()
    states = {state.value: 0 for state in AssetState}
    for state, count in rows:
        if state in states:
            states[state] = int(count)
    totals = (await session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case(
                (vault_assets.c.deletion_attempts >= 8, 1),
                else_=0,
            )), 0),
            func.coalesce(func.sum(case(
                (
                    vault_assets.c.expires_at < instant,
                    1,
                ), else_=0,
            )), 0),
        ).where(vault_assets.c.state != AssetState.DELETED.value)
    )).one()
    expired = int(totals[2])
    exhausted = int(totals[1])
    launch = photo_launch_preflight(config)
    capability = upload_capability()
    blockers = tuple(launch["missing"]) + (
        "photo_upload_not_implemented",
        "photo_processing_not_implemented",
        "background_retention_not_scheduled",
    )
    return PrivateVaultAudit(
        checked_at=instant.isoformat(),
        by_state=states,
        expired_not_deleted=expired,
        exhausted_retries=exhausted,
        pending_over_24h=0,
        requires_operator_attention=bool(expired or exhausted),
        photo_upload_enabled=bool(capability["enabled"]),
        photo_processing_enabled=bool(launch["photo_processing_enabled"]),
        automatic_deletion_enabled=bool(launch["automatic_deletion_enabled"]),
        launch_blockers=blockers,
    )
