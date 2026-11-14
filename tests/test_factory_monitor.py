"""Storage monitor checks actual usage and notifies configured owners."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.factory_monitor import FactoryStorageMonitor


@pytest.mark.asyncio
async def test_disk_monitor_alerts_on_high_pressure(tmp_path):
    bot = AsyncMock()
    monitor = FactoryStorageMonitor(bot, tmp_path, (42,))
    with patch("app.services.factory_monitor.shutil.disk_usage", return_value=(100, 86, 14)):
        assert await monitor.check_once() == 86
        assert await monitor.check_once() == 86
    assert bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_disk_monitor_handles_missing_storage(tmp_path):
    bot = AsyncMock()
    monitor = FactoryStorageMonitor(bot, tmp_path / "missing", (42,))
    assert await monitor.check_once() is None
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_lifecycle(tmp_path):
    bot = AsyncMock()
    monitor = FactoryStorageMonitor(bot, tmp_path, (), interval_seconds=60)
    await monitor.start()
    await monitor.start()
    await monitor.stop()
