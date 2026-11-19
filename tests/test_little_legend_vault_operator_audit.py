"""Privacy contract and operator audit regression tests."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.little_legend.privacy_lifecycle import PrivacyLaunchConfig
from app.little_legend.secure_vault import AssetState, upload_capability
from app.little_legend.vault_operator_audit import audit_private_vault


def test_photo_capability_remains_disabled():
    capability = upload_capability()
    assert capability["enabled"] is False
    assert capability["storage_backend_connected"] is False


@pytest.mark.asyncio
async def test_audit_is_aggregate_only_and_launch_is_fail_closed():
    session = AsyncMock()
    grouped = Mock()
    grouped.all.return_value = [
        (AssetState.DELETION_PENDING.value, 3),
        (AssetState.DELETED.value, 4),
    ]
    totals = Mock()
    totals.one.return_value = (5, 2, 5)
    old = Mock()
    old.scalar_one.return_value = 2
    session.execute.side_effect = [grouped, totals, old]
    audit = await audit_private_vault(
        session, config=PrivacyLaunchConfig(),
        now=datetime(2026, 11, 19, tzinfo=UTC),
    )
    assert audit.by_state["deletion_pending"] == 3
    assert audit.by_state["deleted"] == 4
    assert audit.expired_not_deleted == 5
    assert audit.exhausted_retries == 2
    assert audit.pending_over_24h == 2
    assert audit.requires_operator_attention
    assert not audit.photo_upload_enabled
    assert not audit.photo_processing_enabled
    assert not audit.automatic_deletion_enabled
    assert "background_retention_not_scheduled" in audit.launch_blockers
    assert "object_key" not in str(audit)
    assert "owner_id" not in str(audit)


@pytest.mark.asyncio
async def test_audit_rejects_naive_time_without_querying_database():
    session = AsyncMock()
    with pytest.raises(ValueError, match="Timezone-aware"):
        await audit_private_vault(
            session, config=PrivacyLaunchConfig(),
            now=datetime(2026, 11, 19),
        )
    session.execute.assert_not_called()
