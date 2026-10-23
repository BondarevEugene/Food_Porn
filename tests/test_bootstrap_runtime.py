"""Bootstrap regression checks with real FastAPI, aiogram and Uvicorn."""

import asyncio
import errno
import signal
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import uvicorn
from aiogram import Bot, Dispatcher
from fastapi import FastAPI

import main as bootstrap


async def test_application_identity_and_routes():
    import httpx

    from app.admin_app import app
    from app.main import app as compatibility_app

    assert bootstrap.app is app is compatibility_app
    assert sum(getattr(route, "path", None) == "/admin" for route in app.routes) == 1
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/miniapp")).status_code == 200


def test_port_collision_and_release():
    listener = bootstrap.reserve_miniapp_port(0)
    port = listener.getsockname()[1]
    assert listener.getblocking() is False
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            bootstrap.reserve_miniapp_port(port)
    finally:
        listener.close()
    replacement = bootstrap.reserve_miniapp_port(port)
    replacement.close()


def test_permission_failure_has_correct_diagnostic(monkeypatch):
    class Listener:
        closed = False

        def setsockopt(self, *args):
            pass

        def bind(self, address):
            raise OSError(errno.EACCES, "permission denied")

        def close(self):
            self.closed = True

    listener = Listener()
    monkeypatch.setattr(bootstrap.socket, "socket", lambda *args: listener)
    with pytest.raises(RuntimeError, match="Cannot bind"):
        bootstrap.reserve_miniapp_port(8080)
    assert listener.closed


@pytest.mark.parametrize("url", ["", "https://example.org/miniapp"])
async def test_telegram_commands_and_button(url):
    bot = SimpleNamespace(set_my_commands=AsyncMock(), set_chat_menu_button=AsyncMock())
    await bootstrap.configure_telegram(bot, SimpleNamespace(miniapp_url=url))
    commands = bot.set_my_commands.call_args.args[0]
    assert [cmd.command for cmd in commands] == ["start", "history", "admin"]
    button = bot.set_chat_menu_button.call_args.kwargs["menu_button"]
    assert button.type == "commands"


@pytest.mark.parametrize("failure", ["telegram", "pipeline", "services", None])
async def test_resources_close_on_startup_failure_and_normal_exit(monkeypatch, failure):
    listener = bootstrap.reserve_miniapp_port(0)
    database = SimpleNamespace(session_factory=object(), engine=object(), close=AsyncMock())
    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
    pipeline = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    dispatcher = SimpleNamespace(fsm=SimpleNamespace(close=AsyncMock()))
    settings = SimpleNamespace(
        log_level="INFO",
        miniapp_port=listener.getsockname()[1],
        app_env="test",
        bot_token="123:test",
        validate_runtime=lambda: None,
        ensure_directories=lambda: None,
    )
    configure = AsyncMock()
    services = AsyncMock()
    if failure == "telegram":
        configure.side_effect = RuntimeError("telegram failure")
    elif failure == "pipeline":
        pipeline.start.side_effect = RuntimeError("pipeline failure")
    elif failure == "services":
        services.side_effect = RuntimeError("services failure")
    admin_close = AsyncMock()
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "reserve_miniapp_port", lambda port: listener)
    monkeypatch.setattr(bootstrap, "Database", lambda settings: database)
    monkeypatch.setattr(bootstrap, "Bot", lambda **kwargs: bot)
    monkeypatch.setattr(bootstrap, "MenuPipeline", lambda **kwargs: pipeline)
    monkeypatch.setattr(bootstrap, "create_dispatcher", lambda *args: dispatcher)
    monkeypatch.setattr(bootstrap, "configure_telegram", configure)
    monkeypatch.setattr(bootstrap, "run_services", services)
    monkeypatch.setattr(bootstrap, "admin_engine", SimpleNamespace(dispose=admin_close))
    if failure:
        with pytest.raises(RuntimeError, match=failure):
            await bootstrap.main()
    else:
        await bootstrap.main()
    for close in [
        database.close,
        admin_close,
        bot.session.close,
        pipeline.stop,
        dispatcher.fsm.close,
    ]:
        close.assert_awaited_once()
    assert listener.fileno() == -1
    assert bootstrap.app.state.pipeline is None
    assert bootstrap.app.state.bot is None


async def test_cleanup_error_does_not_skip_next_resource(caplog):
    close = AsyncMock(side_effect=ValueError("cannot close"))
    await bootstrap.close_resource("broken", close)
    assert "Could not close broken" in caplog.text


async def test_cleanup_timeout(monkeypatch, caplog):
    monkeypatch.setattr(bootstrap, "SHUTDOWN_TIMEOUT", 0.01)

    async def blocked():
        await asyncio.Event().wait()

    await bootstrap.close_resource("blocked", blocked)
    assert "Shutdown timeout: blocked" in caplog.text


async def test_uvicorn_startup_exit_becomes_runtime_error():
    class FailedServer:
        async def serve(self, **kwargs):
            raise SystemExit(3)

    with pytest.raises(RuntimeError, match="exit=3"):
        await bootstrap.serve_web(FailedServer(), None)


@pytest.mark.parametrize("failure", ["web", "poll"])
async def test_service_failure_stops_its_peer(monkeypatch, failure):
    events = {}

    @contextmanager
    def signals(event):
        events["stop"] = event
        yield

    monkeypatch.setattr(bootstrap, "shutdown_signals", signals)
    server = SimpleNamespace(started=False, should_exit=False, force_exit=False)
    poll_stopped = asyncio.Event()
    web_stopped = asyncio.Event()

    async def web(**kwargs):
        try:
            server.started = True
            if failure == "web":
                await asyncio.sleep(0.08)
                raise ValueError("web failed")
            while not server.should_exit:
                await asyncio.sleep(0.001)
        finally:
            web_stopped.set()

    server.serve = web

    async def poll(*args, **kwargs):
        try:
            assert kwargs["handle_signals"] is False
            assert kwargs["close_bot_session"] is False
            if failure == "poll":
                raise ValueError("poll failed")
            await poll_stopped.wait()
        finally:
            poll_stopped.set()

    async def stop_poll():
        poll_stopped.set()

    dispatcher = SimpleNamespace(
        start_polling=poll,
        stop_polling=stop_poll,
        resolve_used_update_types=lambda: [],
    )
    with pytest.raises(ValueError, match=failure):
        await bootstrap.run_services(server, None, None, dispatcher)
    assert server.should_exit
    assert web_stopped.is_set()
    assert poll_stopped.is_set()


async def test_web_start_timeout_stops_server(monkeypatch):
    monkeypatch.setattr(bootstrap, "WEB_START_TIMEOUT", 0.01)
    server = SimpleNamespace(started=False, should_exit=False, force_exit=False)
    stopped = asyncio.Event()

    async def web(**kwargs):
        try:
            while not server.should_exit:
                await asyncio.sleep(0.001)
        finally:
            stopped.set()

    server.serve = web
    with pytest.raises(TimeoutError):
        await bootstrap.run_services(server, None, None, SimpleNamespace())
    assert stopped.is_set()


async def test_real_http_polling_and_sigterm_cleanup(monkeypatch):
    import httpx

    api = FastAPI()

    @api.get("/probe")
    async def probe():
        return {"ok": True}

    listener = bootstrap.reserve_miniapp_port(0)
    port = listener.getsockname()[1]
    server = bootstrap.ApplicationServer(uvicorn.Config(api, log_level="error"))
    bot = Bot("123:test")
    dispatcher = Dispatcher()
    poll_started = asyncio.Event()
    poll_stopped = asyncio.Event()

    async def polling(**kwargs):
        try:
            poll_started.set()
            await asyncio.Event().wait()
        finally:
            poll_stopped.set()

    monkeypatch.setattr(dispatcher, "_polling", polling)
    previous = signal.getsignal(signal.SIGTERM)
    task = asyncio.create_task(bootstrap.run_services(server, listener, bot, dispatcher))
    try:
        await asyncio.wait_for(poll_started.wait(), timeout=3)
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"http://127.0.0.1:{port}/probe")
        assert response.json() == {"ok": True}
        # os.kill(..., SIGTERM) uses TerminateProcess on Windows and bypasses
        # Python's shutdown handler. raise_signal exercises it on both platforms.
        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(task, timeout=3)
        assert poll_stopped.is_set()
        assert signal.getsignal(signal.SIGTERM) == previous
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        listener.close()
        await bot.session.close()


async def test_main_cancellation_stops_real_dispatcher(monkeypatch):
    server = SimpleNamespace(started=False, should_exit=False, force_exit=False)

    async def web(**kwargs):
        server.started = True
        while not server.should_exit:
            await asyncio.sleep(0.001)

    server.serve = web
    bot = Bot("123:test")
    dispatcher = Dispatcher()
    ready = asyncio.Event()
    closed = asyncio.Event()

    async def poll(**kwargs):
        try:
            ready.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(dispatcher, "_polling", poll)
    task = asyncio.create_task(bootstrap.run_services(server, None, bot, dispatcher))
    await asyncio.wait_for(ready.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert server.should_exit
    await bot.session.close()
