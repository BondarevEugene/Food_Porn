"""Temporary video archive retention without touching paid order history."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.video_retention import MAX_AGE, MAX_VIDEOS, prune_video_archive


class FakeSession:
    def __init__(self, orders):
        self.orders = orders
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def scalars(self, _statement):
        return SimpleNamespace(all=lambda: sorted(
            [o for o in self.orders if o.status == "ready" and o.output_path],
            key=lambda o: (o.updated_at, o.id), reverse=True,
        ))

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_prunes_old_and_overflow_videos_preserving_orders(tmp_path):
    now = datetime.now(UTC)
    folder = tmp_path / "video_orders"
    folder.mkdir()
    orders = []
    for i in range(1, 34):
        path = folder / f"video_story_{i}.mp4"
        path.write_bytes(b"mp4")
        age = timedelta(hours=25) if i == 1 else timedelta(minutes=33 - i)
        orders.append(SimpleNamespace(
            id=i, output_path=str(path), updated_at=now-age,
            status="ready", paid_at=now-timedelta(days=2),
        ))
    session = FakeSession(orders)
    removed = await prune_video_archive(lambda: session, now=now)
    assert removed == 3
    assert sum(Path(o.output_path).is_file() for o in orders if o.output_path) == 30
    assert orders[0].output_path is None
    assert orders[0].status == "ready"
    assert orders[0].paid_at is not None
    assert session.committed


@pytest.mark.asyncio
async def test_does_not_delete_unexpected_paths(tmp_path):
    now = datetime.now(UTC)
    path = tmp_path / "important.mp4"
    path.write_bytes(b"keep")
    order = SimpleNamespace(
        id=1, output_path=str(path), updated_at=now-MAX_AGE-timedelta(seconds=1),
        status="ready",
    )
    removed = await prune_video_archive(lambda: FakeSession([order]), now=now)
    assert removed == 0
    assert path.read_bytes() == b"keep"
    assert order.output_path == str(path)


def test_archive_limits():
    assert MAX_VIDEOS == 30
    assert MAX_AGE == timedelta(hours=24)
