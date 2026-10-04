"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS

Module: Application Bootstrap (main.py)
Layer: Application Core

Description: Точка входа в приложение. Инициализирует
настройки, базу данных, бота, диспетчер, фоновые процессы,
FastAPI вебхуки и админ-панель (sqladmin).
==========================================================
"""

from __future__ import annotations

import asyncio
import logging
import socket

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from fastapi import FastAPI
from sqladmin import Admin

# Вебхуки
from src.payment.portmone.router import router as portmone_router

# Роутери бота
from app.bot.handlers import menu, payment, registration, stars, start
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.wallpaper import router as wallpaper_router

# Основные компоненты системы
from app.config import get_settings
from app.database.session import Database
from app.miniapp.api import router as miniapp_router
from app.workers.menu_pipeline import MenuPipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="Food_Porn & Old Money API", version="2.0")
app.include_router(portmone_router)
app.include_router(miniapp_router)

# Админпанель
from app.admin_app import app, admin


def reserve_miniapp_port(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("0.0.0.0", port))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError as exc:
        listener.close()
        raise RuntimeError(
            f"Mini App port {port} is already in use. Stop that process or choose "
            "MINIAPP_PORT and point the Cloudflare tunnel to the same port."
        ) from exc


async def main() -> None:
    settings = get_settings()
    settings.validate_runtime()
    settings.ensure_directories()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.info("System Boot: Initializing Food_Porn & Old Money Ecosystem...")

    web_port = settings.miniapp_port or 8000
    listener = reserve_miniapp_port(web_port)

    database = Database(settings)

    try:
        admin = Admin(app, database.engine)
        logger.info("SQLAdmin successfully mounted at /admin")
    except Exception as e:
        logger.error(f"Failed to initialize SQLAdmin: {e}")

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
    app.state.pipeline = pipeline
    app.state.bot = bot

    dispatcher["settings"] = settings
    dispatcher["session_factory"] = database.session_factory
    dispatcher["pipeline"] = pipeline

    dispatcher.include_router(admin_router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(menu.router)
    dispatcher.include_router(wallpaper_router)
    dispatcher.include_router(payment.router)
    dispatcher.include_router(stars.router)

    commands = [BotCommand(command="start", description="Відкрити майстерню")]
    if not settings.miniapp_url:
        commands.extend([
            BotCommand(command="new", description="Створити новий сет / маніфестацію"),
            BotCommand(command="admin", description="Панель керування"),
        ])
    await bot.set_my_commands(commands)
    if settings.miniapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Відкрити подарунки", web_app=WebAppInfo(url=settings.miniapp_url),
        ))

    await pipeline.start()

    server = uvicorn.Server(uvicorn.Config(
        app, host="0.0.0.0", port=web_port, log_level="info",
    ))
    web_task = asyncio.create_task(server.serve(sockets=[listener]))

    logger.info(
        f"System Ready: Bot is polling & Web Server running on port {web_port} (Admin: http://localhost:{web_port}/admin)...")
    poll_tag = dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    poll_task = asyncio.create_task(poll_tag)

    try:
        done, _ = await asyncio.wait({poll_task, web_task}, return_when=asyncio.FIRST_COMPLETED)
        if web_task in done:
            if not poll_task.done():
                poll_task.cancel()
                await asyncio.gather(poll_task, return_exceptions=True)
            await web_task
            raise RuntimeError("Web server stopped; bot polling was also stopped")
        await poll_task
    finally:
        try:
            if server is not None:
                server.should_exit = True
                await web_task
        finally:
            if listener is not None:
                listener.close()
            logger.info("System Shutdown: Closing connections...")
            await pipeline.stop()
            await database.close()
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped manually.")
