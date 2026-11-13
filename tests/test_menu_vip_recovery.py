"""Regression tests: VIP menu delivery and rollback-safe crash recovery."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import (
    Base,
    Customer,
    ItemCategory,
    Language,
    Menu,
    MenuItem,
    MenuStatus,
)
from app.database.repositories import MenuRepository
from app.bot.handlers.menu import MenuAction, confirm_generation


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + str(tmp_path / "vip-menu.db")
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(Customer(
            id=1, telegram_user_id=725003786, name="Owner",
            phone="+380001", language=Language.RU,
            country="UA", city="Kyiv",
        ))
        session.add_all([
            Menu(id=98, customer_id=1, status=MenuStatus.QUEUED),
            Menu(id=99, customer_id=1, status=MenuStatus.DRAFT),
            Menu(
                id=100, customer_id=1,
                status=MenuStatus.WAITING_FOR_PAYMENT,
                is_paid=True, payment_system="wayforpay",
                payment_id="verified-receipt",
            ),
        ])
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_vip_bypass_does_not_require_payment_invoice(db):
    async with db() as session:
        repo = MenuRepository(session)
        assert await repo.grant_vip_menu_access(98)
        menu = await repo.get(98)
        assert menu.is_paid is True
        assert menu.payment_system == "vip_bypass"
        assert menu.payment_id == "VIP_PASS_98"
        assert menu.status == MenuStatus.PAID
        assert menu.paid_at is not None
        # Repeated VIP processing does not create a second payment.
        original = menu.paid_at
        assert await repo.grant_vip_menu_access(98)
        assert (await repo.get(98)).paid_at == original


@pytest.mark.asyncio
async def test_vip_bypass_does_not_override_commercial_payment(db):
    async with db() as session:
        repo = MenuRepository(session)
        assert not await repo.grant_vip_menu_access(100)
        menu = await repo.get(100)
        assert menu.payment_id == "verified-receipt"
        assert menu.payment_system == "wayforpay"


@pytest.mark.asyncio
async def test_vip_bypass_rejects_unqueued_draft(db):
    async with db() as session:
        repo = MenuRepository(session)
        with pytest.raises(ValueError, match="cannot receive VIP bypass"):
            await repo.grant_vip_menu_access(99)
        menu = await repo.get(99)
        assert menu.is_paid is False


@pytest.mark.asyncio
async def test_regular_payment_still_requires_verified_invoice(db):
    async with db() as session:
        repo = MenuRepository(session)
        with pytest.raises(ValueError, match="has no payable invoice"):
            await repo.mark_as_paid(
                98, payment_id="unverified", payment_system="wayforpay",
            )


@pytest.mark.asyncio
async def test_stale_queued_menu_can_be_resumed_without_new_order(db):
    async with db() as session:
        menu = await MenuRepository(session).get(98)
        menu.cover_photo_path = "/uploads/cover.jpg"
        menu.spread_photo_path = "/uploads/spread.jpg"
        session.add(MenuItem(
            menu_id=98, category=ItemCategory.MAIN,
            title="Soup", position=1,
        ))
        await session.commit()

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=725003786),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    pipeline = SimpleNamespace(submit=AsyncMock(return_value=True))
    state = SimpleNamespace(clear=AsyncMock())
    await confirm_generation(
        callback, MenuAction(action="generate", menu_id=98),
        state, db, pipeline,
    )
    pipeline.submit.assert_awaited_once_with(98, 725003786)
    callback.answer.assert_awaited_once()
    assert "Повторно" in callback.answer.await_args.args[0]
    callback.message.edit_text.assert_not_awaited()
    async with db() as session:
        assert (await MenuRepository(session).get(98)).status == MenuStatus.QUEUED


@pytest.mark.asyncio
async def test_active_queued_menu_is_not_resubmitted(db):
    from datetime import UTC, datetime, timedelta

    async with db() as session:
        menu = await MenuRepository(session).get(98)
        menu.processing_token = "active-lease"
        menu.processing_lease_until = datetime.now(UTC) + timedelta(minutes=4)
        await session.commit()

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=725003786),
        answer=AsyncMock(),
    )
    pipeline = SimpleNamespace(submit=AsyncMock())
    await confirm_generation(
        callback, MenuAction(action="generate", menu_id=98),
        SimpleNamespace(clear=AsyncMock()), db, pipeline,
    )
    pipeline.submit.assert_not_awaited()
    assert "уже формируется" in callback.answer.await_args.args[0]
