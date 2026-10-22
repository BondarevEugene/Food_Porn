"""Start Food_Porn and a temporary Cloudflare Mini App tunnel together.

Copy this file to the Food_Porn project root and run:
    python start_food_porn_miniapp.py

Keep this terminal open. Send /start to the Telegram bot after startup.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("MINIAPP_PORT", "8081"))
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def cloudflared_executable() -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(local) / "FoodPornTools" / "cloudflared.exe" if local else None,
        ROOT / "cloudflared.exe",
    ]
    for path in candidates:
        if path and path.is_file():
            return str(path)
    found = shutil.which("cloudflared")
    if found:
        return found
    raise RuntimeError("Не найден cloudflared.exe в FoodPornTools или PATH.")


def ensure_port_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("0.0.0.0", PORT))
        except OSError as exc:
            raise RuntimeError(
                f"Порт {PORT} занят. Остановите прежний запуск бота (Ctrl+C) "
                "или задайте другой MINIAPP_PORT."
            ) from exc


def read_tunnel_output(process: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        lines.put(line.rstrip("\r\n"))


def wait_for_tunnel(process: subprocess.Popen[str], lines: queue.Queue[str]) -> str:
    url = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Cloudflare Tunnel завершился до подключения.")
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            continue
        found = TUNNEL_URL.search(line)
        if found:
            url = found.group(0)
        if "Registered tunnel connection" in line and url:
            return url
        if " ERR " in line:
            print("Cloudflare:", line, flush=True)
    raise RuntimeError("Туннель не подключился за 90 секунд.")


def stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def wait_for_page(url: str, bot: subprocess.Popen[str], tunnel: subprocess.Popen[str], seconds: int) -> None:
    deadline = time.monotonic() + seconds
    last_error = "нет ответа"
    while time.monotonic() < deadline:
        if bot.poll() is not None:
            raise RuntimeError("Бот завершился во время проверки Mini App. Смотрите ошибку выше.")
        if tunnel.poll() is not None:
            raise RuntimeError("Cloudflare Tunnel отключился во время проверки Mini App.")
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc.reason if isinstance(exc, urllib.error.URLError) else exc)
        time.sleep(2)
    raise RuntimeError(f"Адрес {url} недоступен: {last_error}")


def public_page_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    if not (ROOT / "run.py").is_file() or not (ROOT / "app" / "miniapp" / "api.py").is_file():
        raise RuntimeError("Положите этот файл в корень проекта Food_Porn, рядом с run.py.")
    ensure_port_free()
    tunnel = subprocess.Popen(
        [cloudflared_executable(), "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )
    bot = None
    try:
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=read_tunnel_output, args=(tunnel, lines), daemon=True).start()
        public_url = wait_for_tunnel(tunnel, lines) + "/miniapp"
        env = os.environ.copy()
        env["MINIAPP_PORT"] = str(PORT)
        env["MINIAPP_URL"] = public_url
        print("Запускаю бот и проверяю новый адрес Mini App...", flush=True)
        # Runtime validation stays in app.main; full pytest/Ruff diagnostics can be
        # run separately with `python launcher.py diagnose` when desired.
        bot = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env)
        wait_for_page(f"http://127.0.0.1:{PORT}/miniapp", bot, tunnel, 90)
        wait_for_page(public_url, bot, tunnel, 75)
        print("\n" + "=" * 64, flush=True)
        print(f"НОВЫЙ АДРЕС MINI APP: {public_url}", flush=True)
        print("Локальный и публичный адреса отвечают HTTP 200.", flush=True)
        print("Отправьте боту НОВЫЙ /start и нажмите кнопку в новом сообщении.", flush=True)
        print("Старые сообщения бота содержат прежний адрес и больше не откроются.", flush=True)
        print("Оставьте это окно открытым. Для остановки нажмите Ctrl+C.", flush=True)
        print("=" * 64 + "\n", flush=True)
        next_health_check = time.monotonic() + 30
        missed_checks = 0
        while True:
            if bot.poll() is not None:
                print("Бот остановился. Проверьте ошибку выше.", flush=True)
                return bot.returncode or 1
            if tunnel.poll() is not None:
                print("Туннель отключился. Останавливаю бот: старый адрес больше не работает.", flush=True)
                return 1
            if time.monotonic() >= next_health_check:
                missed_checks = 0 if public_page_is_ready(public_url) else missed_checks + 1
                if missed_checks == 1:
                    print("Публичный адрес временно не отвечает. Проверяю повторно...", flush=True)
                if missed_checks >= 3:
                    print("Туннель потерял связь с Cloudflare. Этот адрес больше недоступен. "
                          "Запустите файл снова и отправьте боту новый /start.", flush=True)
                    return 1
                next_health_check = time.monotonic() + 30
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nОстанавливаю бот и туннель...", flush=True)
        return 0
    finally:
        stop(bot)
        stop(tunnel)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"Ошибка запуска: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
