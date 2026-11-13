"""Regression: world cuisine selection must not lazy-load expired ORM IDs."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers.menu import MenuAction, apply_cuisine
from app.database.models import Base, Customer, Language, Menu, MenuStatus
from app.database.repositories import MenuRepository


@pytest.mark.asyncio
async def test_choose_world_cuisine_survives_sqlalchemy_expire_all(tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + str(tmp_path / "cuisine.db")
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(
                Customer(
                    id=1, telegram_user_id=123456, phone="+380123456789",
                    name="Guest", language=Language.RU,
                    country="Ukraine", city="Kyiv",
                )
            )
            session.add(Menu(id=98, customer_id=1, status=MenuStatus.DRAFT))
            await session.commit()

        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=123456),
            message=SimpleNamespace(edit_text=AsyncMock()),
            answer=AsyncMock(),
        )
        await apply_cuisine(
            callback,
            MenuAction(action="cuisine", menu_id=98, category="italian"),
            factory,
        )
        callback.message.edit_text.assert_awaited_once()
        assert "Капрезе" in callback.message.edit_text.await_args.args[0]
        callback.answer.assert_awaited_once()
        async with factory() as session:
            saved = await MenuRepository(session).get(98, full=True)
            assert len(saved.items) == 6
            assert any(item.title == "Тирамису" for item in saved.items)
            assert saved.status == MenuStatus.DRAFT
    finally:
        await engine.dispose()
