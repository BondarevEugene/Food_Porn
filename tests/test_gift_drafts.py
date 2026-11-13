"""Unpaid gift drafts survive restarts without granting paid files."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.models import CRMBase
from app.services.gift_drafts import load_gift_draft, store_gift_draft


@pytest.mark.asyncio
async def test_gift_draft_roundtrip_and_idempotent_update(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "drafts.db"))
    async with engine.begin() as connection:
        await connection.run_sync(CRMBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo")
    await store_gift_draft(
        factory, user_id=42, product_choice=None, photo_paths=[photo],
        goals=[], style="dark", language="ru", stage="product",
    )
    await store_gift_draft(
        factory, user_id=42, product_choice="both", photo_paths=[photo],
        goals=["dream"] * 5, style="light", language="ru", stage="ready",
    )
    loaded = await load_gift_draft(factory, 42)
    assert loaded is not None
    assert loaded.product_choice == "both"
    assert loaded.stage == "ready"
    assert loaded.goals == ["dream"] * 5
    assert loaded.photo_paths == [str(photo)]
    assert await load_gift_draft(factory, 1001) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_gift_draft_rejects_invalid_choice_and_relative_paths(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "drafts.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    with pytest.raises(ValueError, match="product"):
        await store_gift_draft(
            factory, user_id=42, product_choice="invalid", photo_paths=[],
            goals=[], style="dark", language="ru", stage="product",
        )
    with pytest.raises(ValueError, match="absolute"):
        await store_gift_draft(
            factory, user_id=42, product_choice="video", photo_paths=[Path("relative.jpg")],
            goals=[], style="dark", language="ru", stage="product",
        )
    await engine.dispose()
