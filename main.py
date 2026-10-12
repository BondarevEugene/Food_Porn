"""Запуск Food_Porn: Telegram, Mini App, платежные API и SQLAdmin.

Импорт ``main.app`` подключает HTTP-маршруты, но не запускает polling или
воркеры. Для запуска всей системы используйте ``python launcher.py start``.
SQLAdmin и его приложение создаются только в ``app.admin_app``.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import signal
import socket
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AsyncExitStack, contextmanager
from types import FrameType

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from app.admin_app import app
from app.admin_app import engine as admin_engine
from app.bot.handlers import menu, payment, registration, stars, start
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.wallpaper import router as wallpaper_router
from app.config import Settings, get_settings
from app.database.session import Database
from app.miniapp.api import router as miniapp_router
from app.workers.menu_pipeline import MenuPipeline
from src.payment.portmone.router import router as portmone_router

logger = logging.getLogger(__name__)

WEB_HOST = "0.0.0.0"
WEB_START_TIMEOUT = 30.0
SHUTDOWN_TIMEOUT = 15.0

# Сохраняем объект приложения, его авторизацию и startup-обработчики.
app.include_router(portmone_router)
app.include_router(miniapp_router)


class ApplicationServer(uvicorn.Server):
    """Сигналами управляет bootstrap, а не отдельный HTTP-сервер."""

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    # Не заменяем обработчики, которые мог установить launcher.
    logging.getLogger().setLevel(level)


def reserve_miniapp_port(port: int) -> socket.socket:
    """Резервирует порт до обращения к Telegram и создания воркеров."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # На Windows запрещаем второму процессу занять тот же адрес.
        # SO_REUSEADDR здесь намеренно не используется.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((WEB_HOST, port))
        listener.listen(socket.SOMAXCONN)
        listener.setblocking(False)
    except OSError as exc:
        listener.close()
        if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
            raise RuntimeError(
                f"Mini App port {port} is already in use. Stop that process or choose "
                "MINIAPP_PORT and point the Cloudflare tunnel to the same port."
            ) from exc
        raise RuntimeError(f"Cannot bind Mini App to {WEB_HOST}:{port}: {exc}") from exc
    return listener


def create_dispatcher(settings: Settings, database: Database, pipeline: MenuPipeline) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings
    dispatcher["session_factory"] = database.session_factory
    dispatcher["pipeline"] = pipeline
    # Порядок важен: сохраняем приоритет обработчиков действующего бота.
    dispatcher.include_routers(
        admin_router,
        start.router,
        registration.router,
        menu.router,
        wallpaper_router,
        payment.router,
        stars.router,
    )
    return dispatcher


async def configure_telegram(bot: Bot, settings: Settings) -> None:
    commands = [BotCommand(command="start", description="Відкрити майстерню")]
    if settings.miniapp_url:
        menu_button = MenuButtonWebApp(
            text="Відкрити подарунки",
            web_app=WebAppInfo(url=settings.miniapp_url),
        )
    else:
        commands.extend(
            [
                BotCommand(command="new", description="Створити новий сет / маніфестацію"),
                BotCommand(command="admin", description="Панель керування"),
            ]
        )
        # После отключения Mini App убираем сохраненную Telegram web-кнопку.
        menu_button = MenuButtonCommands()
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=menu_button)


@contextmanager
def shutdown_signals(stop_event: asyncio.Event) -> Iterator[None]:
    """Общий обработчик Ctrl+C / SIGTERM, включая Windows."""
    loop = asyncio.get_running_loop()
    previous = {}

    def request_shutdown(signum: int, _frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    try:
        for signum in signals:
            previous[signum] = signal.signal(signum, request_shutdown)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


async def close_resource(name: str, close: Callable[[], Awaitable[object]]) -> None:
    """Ошибка одной очистки не мешает закрыть остальные ресурсы."""
    try:
        async with asyncio.timeout(SHUTDOWN_TIMEOUT):
            await close()
    except TimeoutError:
        logger.error("Shutdown timeout: %s", name)
    except Exception:
        logger.exception("Could not close %s", name)


async def serve_web(server: uvicorn.Server, listener: socket.socket) -> None:
    try:
        await server.serve(sockets=[listener])
    except SystemExit as exc:
        # Uvicorn может вызвать sys.exit при ошибке ASGI startup.
        # Превращаем это в обычную ошибку, чтобы bootstrap освободил ресурсы.
        raise RuntimeError(f"Web server startup failed (exit={exc.code})") from exc


async def wait_for_web_start(
    server: uvicorn.Server, web_task: asyncio.Task[None], stop_event: asyncio.Event
) -> bool:
    async with asyncio.timeout(WEB_START_TIMEOUT):
        while not server.started:
            if web_task.done():
                await web_task
                raise RuntimeError("Web server stopped before startup completed")
            if stop_event.is_set():
                return False
            await asyncio.sleep(0.05)
    return True


async def stop_services(
    server: uvicorn.Server,
    dispatcher: Dispatcher,
    web_task: asyncio.Task[None],
    poll_task: asyncio.Task[None] | None,
) -> None:
    server.should_exit = True
    if poll_task is not None and not poll_task.done():
        await close_resource("Telegram polling", dispatcher.stop_polling)

    tasks = [web_task]
    if poll_task is not None:
        tasks.append(poll_task)
    _, pending = await asyncio.wait(tasks, timeout=SHUTDOWN_TIMEOUT)
    if pending:
        logger.warning("Cancelling services after shutdown timeout")
        server.force_exit = True
        for task in pending:
            task.cancel()
    # Забираем результаты и исключения всех задач, включая уже завершенные.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for task, result in zip(tasks, results, strict=True):
        if isinstance(result, Exception):
            logger.error("Service %s stopped with an error: %s", task.get_name(), result)


async def run_services(
    server: uvicorn.Server, listener: socket.socket, bot: Bot, dispatcher: Dispatcher
) -> None:
    stop_event = asyncio.Event()
    poll_task = None
    with shutdown_signals(stop_event):
        web_task = asyncio.create_task(serve_web(server, listener), name="foodporn-web")
        try:
            if not await wait_for_web_start(server, web_task, stop_event):
                return
            if stop_event.is_set():
                return
            poll_task = asyncio.create_task(
                dispatcher.start_polling(
                    bot,
                    allowed_updates=dispatcher.resolve_used_update_types(),
                    handle_signals=False,
                    close_bot_session=False,
                ),
                name="foodporn-telegram",
            )
            stop_task = asyncio.create_task(stop_event.wait(), name="foodporn-shutdown")
            try:
                logger.info("Web server ready; Telegram polling starting")
                done, _ = await asyncio.wait(
                    {web_task, poll_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                # Ошибка сервиса не превращается в успешное завершение,
                # даже если одновременно пришел сигнал остановки.
                for task in (web_task, poll_task):
                    if task in done:
                        await task
                        if not stop_event.is_set():
                            raise RuntimeError(f"Service {task.get_name()} stopped unexpectedly")
            finally:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)
        finally:
            logger.info("Stopping Telegram polling and web server...")
            await stop_services(server, dispatcher, web_task, poll_task)


def clear_runtime_state() -> None:
    app.state.pipeline = None
    app.state.bot = None


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime()
    settings.ensure_directories()
    web_port = settings.miniapp_port or 8000
    logger.info("Starting Food_Porn | environment=%s | web_port=%s", settings.app_env, web_port)

    # Каждый созданный ресурс сразу получает обработчик очистки.
    # Выход из стека работает и при ошибке на любом этапе запуска.
    async with AsyncExitStack() as resources:
        listener = reserve_miniapp_port(web_port)
        resources.callback(listener.close)

        database = Database(settings)
        resources.push_async_callback(close_resource, "database", database.close)
        if admin_engine is not database.engine:
            resources.push_async_callback(close_resource, "admin database", admin_engine.dispose)

        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        resources.push_async_callback(close_resource, "Telegram session", bot.session.close)

        pipeline = MenuPipeline(
            bot=bot, settings=settings, session_factory=database.session_factory
        )
        resources.push_async_callback(close_resource, "menu pipeline", pipeline.stop)
        dispatcher = create_dispatcher(settings, database, pipeline)
        resources.push_async_callback(close_resource, "FSM storage", dispatcher.fsm.close)

        app.state.pipeline = pipeline
        app.state.bot = bot
        resources.callback(clear_runtime_state)

        await configure_telegram(bot, settings)
        await pipeline.start()
        server = ApplicationServer(
            uvicorn.Config(
                app,
                host=WEB_HOST,
                port=web_port,
                log_level=settings.log_level.lower(),
                log_config=None,
                timeout_graceful_shutdown=SHUTDOWN_TIMEOUT,
            )
        )
        logger.info("Mini App: http://localhost:%s/miniapp | Admin: /admin", web_port)
        await run_services(server, listener, bot, dispatcher)
    logger.info("Application stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception:
        logger.exception("Application failed")
        raise SystemExit(1) from None
