"""R2 book inventory: durable keys, grouping, fail-closed deletion."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.crm.r2_book_inventory import associate_books
from app.little_legend.generated_art_store import illustration_key
from app.little_legend.private_pdf_store import pdf_object_key


@pytest.mark.asyncio
async def test_inventory_groups_known_book_and_protects_unknown_objects():
    art = illustration_key(owner_id=7, story_id=11, job_id="lli_example")
    pdf = pdf_object_key(owner_id=7, story_id=11, pdf_sha256="a" * 64)
    timestamp = datetime(2026, 11, 21, tzinfo=UTC)
    rows = [
        [SimpleNamespace(owner_id=7, story_id=11, job_id="lli_example", status="done")],
        [SimpleNamespace(owner_id=7, story_id=11, pdf_sha256="a" * 64, status="ready")],
        [SimpleNamespace(id=11, owner_id=7, updated_at=timestamp)],
    ]
    session = AsyncMock()
    session.execute.side_effect = [
        Mock(all=Mock(return_value=values)) for values in rows
    ]
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    objects = [
        {"key": art, "bytes": 10},
        {"key": pdf, "bytes": 20},
        {"key": "little-legend/unknown.bin", "bytes": 30},
    ]
    with patch("app.crm.r2_book_inventory.async_session_maker", factory):
        result = await associate_books([
            {"provider": "illustrations", "objects": objects[:1]},
            {"provider": "release", "objects": objects[1:]},
        ])
    assert result["deletion_enabled"] is False
    assert len(result["books"]) == 2
    known = next(row for row in result["books"] if row["story_id"] == 11)
    assert known["file_count"] == 2
    assert known["used_bytes"] == 30
    assert all(file["protected"] for row in result["books"] for file in row["files"])
    assert next(row for row in result["books"] if row["group"] == "unlinked")["used_bytes"] == 30
