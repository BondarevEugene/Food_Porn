"""Regression tests: VIP menu delivery and rollback-safe crash recovery."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import (
    Base, Customer, Language, Menu, MenuStatus,
)
from app.database.repositories import MenuRepository


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
