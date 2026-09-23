"""
==========================================================
FOOD_PORN

Module: Application Bootstrap
Layer: Application Core
==========================================================
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

# Никакого dashboard здесь больше нет, всё внутри menu!
from app.bot.handlers import menu, registration, start
from app.config import get_settings
from app.database.session import Database
from app.workers.menu_pipeline import MenuPipeline


async def main() -> None:
    settings = get_settings()
    settings.validate_runtime()
    settings.ensure_directories()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    database = Database(settings)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    pipeline = MenuPipeline(
        bot=bot,
        settings=settings,
        session_factory=database.session_factory,
    )

    dispatcher["settings"] = settings
    dispatcher["session_factory"] = database.session_factory
    dispatcher["pipeline"] = pipeline

    dispatcher.include_router(start.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(menu.router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="new", description="Создать новый сет"),
            BotCommand(command="history", description="Архив сетов"),
        ]
    )
    await pipeline.start()
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await pipeline.stop()
        await database.close()
        await bot.session.close()
