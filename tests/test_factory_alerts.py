"""Infrastructure alerts are owner-only, rate-limited and retryable."""
from unittest.mock import AsyncMock

import pytest

from app.services.factory_alerts import FactoryAlertNotifier, disk_alert


@pytest.mark.asyncio
async def test_deduplicate_and_owner_only():
    send = AsyncMock()
    notifier = FactoryAlertNotifier(send, (123, 123, -1), cooldown_seconds=60)
    assert await notifier.notify("disk:high", "Disk 85%")
    assert not await notifier.notify("disk:high", "Disk 85%")
    send.assert_awaited_once_with(123, "Disk 85%")


@pytest.mark.asyncio
async def test_failed_send_is_retryable():
    send = AsyncMock(side_effect=[RuntimeError("offline"), None])
    notifier = FactoryAlertNotifier(send, (123,))
    assert not await notifier.notify("worker", "Worker failed")
    assert await notifier.notify("worker", "Worker failed")
    assert send.await_count == 2


@pytest.mark.parametrize("used,level", [(69, None), (70, "disk:warning"), (85, "disk:high"), (95, "disk:critical")])
def test_disk_thresholds(used, level):
    alert = disk_alert(used)
    assert (alert[0] if alert else None) == level
