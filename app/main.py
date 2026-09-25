"""
==========================================================
FOOD_PORN

Module: Application Bootstrap (main.py)
Layer: Application Core

Description: Точка входа в приложение. Инициализирует
настройки, базу данных, бота, диспетчер и фоновые процессы.
==========================================================
"""

from __future__ import annotations

import logging
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

# Импорты маршрутизаторов (хендлеров)
from app.bot.handlers import menu, registration, start
from app.bot.handlers.wallpaper import router as wallpaper_router

# Основные компоненты системы
from app.config import get_settings
from app.database.session import Database
from app.workers.menu_pipeline import MenuPipeline

logger = logging.getLogger(__name__)


async def main() -> None:
    """Главная корутина запуска приложения."""

    # 1. Инициализация настроек и логирования
    settings = get_settings()
    settings.validate_runtime()
    settings.ensure_directories()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.info("System Boot: Initializing Food_Porn Enterprise Control Center...")

    # 2. Инициализация инфраструктуры
    database = Database(settings)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    # 3. Инициализация фонового конвейера (Pipeline)
    pipeline = MenuPipeline(
        bot=bot,
        settings=settings,
        session_factory=database.session_factory,
    )

    # 4. Внедрение зависимостей (Dependency Injection) в диспетчер
    dispatcher["settings"] = settings
    dispatcher["session_factory"] = database.session_factory
    dispatcher["pipeline"] = pipeline

    # 5. Регистрация маршрутов
    dispatcher.include_router(start.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(menu.router)
    dispatcher.include_router(wallpaper_router)  # Модуль AI Манифестаций

    # 6. Настройка командного меню бота
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Головне меню"),
            BotCommand(command="new", description="Створити новий сет"),
            BotCommand(command="history", description="Архів маніфестацій та сетів"),
        ]
    )

    # 7. Запуск процессов
    await pipeline.start()
    try:
        logger.info("System Ready: Bot is polling...")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        # 8. Корректное завершение работы (Graceful Shutdown)
        logger.info("System Shutdown: Closing connections...")
        await pipeline.stop()
        await database.close()
        await bot.session.close()


if __name__ == "__main__":
    # Резервный запуск напрямую (на случай запуска без launcher.py)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped manually.")
