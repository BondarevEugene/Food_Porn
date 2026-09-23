"""
==========================================================
FOOD_PORN

Module: Enterprise Runtime Supervisor & Control Center
Layer: Entry Point / Operations

Responsibilities:
    - Comprehensive environmental and cryptographic validation
    - Real-time diagnostics for Neon PostgreSQL, Telegram, and OpenAI
    - Automated code quality checks (Ruff, Pytest integration)
    - Process supervisor for Telegram Bot polling and FastAPI CRM Admin
    - Interactive operational console with live deep-links
==========================================================
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 11)
DEFAULT_TIMEOUT = 8.0
SUPERVISOR_BUILD = "0202"
REPORT_PATH = ROOT / "storage" / "diagnostics" / "last_report.json"

REQUIRED_FILES = (
    "run.py",
    "app/main.py",
    "app/config.py",
    "app/database/models.py",
    "app/database/session.py",
    "app/services/image_generation.py",
    "app/render/booklet.py",
    "app/admin_app.py",
    "alembic.ini",
    "requirements.txt",
    ".env.example",
)

REQUIRED_PACKAGES = {
    "aiogram": "aiogram",
    "SQLAlchemy": "sqlalchemy",
    "asyncpg": "asyncpg",
    "alembic": "alembic",
    "pydantic-settings": "pydantic_settings",
    "openai": "openai",
    "Pillow": "PIL",
    "reportlab": "reportlab",
    "aiofiles": "aiofiles",
    "phonenumbers": "phonenumbers",
    "greenlet": "greenlet",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqladmin": "sqladmin",
}

CORE_MODULES = (
    "app.config",
    "app.database.models",
    "app.database.session",
    "app.services.image_generation",
    "app.render.booklet",
    "app.workers.menu_pipeline",
    "app.admin_app",
    "app.bot.handlers.start",
    "app.bot.handlers.registration",
    "app.bot.handlers.menu",
    "app.main",
)


class Status(StrEnum):
    """Normalized diagnostic states used by the renderer and JSON report."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    INFO = "INFO"


@dataclass(slots=True)
class CheckResult:
    """One sanitized diagnostic result."""

    section: str
    name: str
    status: Status
    details: str
    duration_ms: float = 0.0
    critical: bool = False
    remedy: str | None = None
    metrics: dict[str, int | float | str | bool] = field(default_factory=dict)


@dataclass(slots=True)
class DiagnosticContext:
    """Shared state accumulated without ever storing raw secrets in reports."""

    offline: bool
    deep: bool
    timeout: float
    settings: Any | None = None
    database_revision: str | None = None
    local_revision: str | None = None
    bot_username: str | None = None


class Theme:
    """ANSI palette with a plain-text fallback for redirected output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    enabled = True

    @classmethod
    def paint(cls, value: str, *styles: str) -> str:
        if not cls.enabled:
            return value
        return "".join(styles) + value + cls.RESET

    @classmethod
    def link(cls, url: str, label: str) -> str:
        """Generates an OSC 8 hyperlink escape sequence for modern terminals."""
        if not cls.enabled:
            return f"{label} ({url})"
        return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"


STATUS_STYLE = {
    Status.PASS: ("✅", Theme.GREEN),
    Status.WARN: ("⚠️ ", Theme.YELLOW),
    Status.FAIL: ("❌", Theme.RED),
    Status.SKIP: ("⏭️ ", Theme.GRAY),
    Status.INFO: ("ℹ️ ", Theme.CYAN),
}


def configure_console(no_color: bool) -> None:
    """Enable Unicode and ANSI colors on modern Windows terminals."""

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    if os.name == "nt":
        os.system("")
    Theme.enabled = not no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ


def terminal_width() -> int:
    return max(82, min(shutil.get_terminal_size((100, 24)).columns, 118))


def visible_len(value: str) -> int:
    ansi = re.compile(r"\x1b\[[0-9;]*m|\x1b\]8;;.*?\x1b\\|\x1b\]8;;\x1b\\")
    return len(ansi.sub("", value))


def pad(value: str, width: int) -> str:
    return value + " " * max(0, width - visible_len(value))


def safe_text(value: object, limit: int = 180) -> str:
    """Flatten untrusted exceptions without leaking connection credentials."""

    text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    text = re.sub(r"(?i)(sk-[a-z0-9_-]{8})[a-z0-9_-]+", r"\1…", text)
    text = re.sub(r"\b\d{6,15}:[A-Za-z0-9_-]{25,}\b", "***:TELEGRAM_TOKEN", text)
    text = re.sub(r"(?i)(bot token|api[_ -]?key|password)(\s*[=:]\s*)\S+", r"\1\2***", text)
    text = re.sub(r"(?i)(postgres(?:ql)?(?:\+asyncpg)?://[^:]+:)[^@]+@", r"\1***@", text)
    return text[:limit] + ("…" if len(text) > limit else "")


def mask_secret(value: str, visible_start: int = 4, visible_end: int = 3) -> str:
    value = value.strip()
    if not value:
        return "не задан"
    if len(value) <= visible_start + visible_end + 4:
        return "•" * len(value)
    return f"{value[:visible_start]}{'•' * 8}{value[-visible_end:]}"


def safe_database_label(database_url: str) -> str:
    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    host = parsed.hostname or "неизвестный-хост"
    database = parsed.path.lstrip("/") or "неизвестная-база"
    return f"postgresql+asyncpg://***@{host}/{database}"


def result(
    section: str,
    name: str,
    status: Status,
    details: str,
    *,
    started: float,
    critical: bool = False,
    remedy: str | None = None,
    metrics: dict[str, int | float | str | bool] | None = None,
) -> CheckResult:
    return CheckResult(
        section=section,
        name=name,
        status=status,
        details=safe_text(details),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        critical=critical,
        remedy=remedy,
        metrics=metrics or {},
    )


def check_python() -> CheckResult:
    started = time.perf_counter()
    current = sys.version_info[:3]
    valid = current >= MIN_PYTHON
    return result(
        "SYSTEM",
        "Python runtime",
        Status.PASS if valid else Status.FAIL,
        f"Python {platform.python_version()} · {platform.machine()} · {sys.executable}",
        started=started,
        critical=True,
        remedy=f"Установите Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} или новее.",
    )


def check_virtual_environment() -> CheckResult:
    started = time.perf_counter()
    active = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return result(
        "SYSTEM",
        "Virtual environment",
        Status.PASS if active else Status.WARN,
        f"{'активировано' if active else 'не активировано'} · prefix={sys.prefix}",
        started=started,
        remedy="PowerShell: .\\.venv\\Scripts\\Activate.ps1",
    )


def check_project_structure() -> CheckResult:
    started = time.perf_counter()
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    status = Status.PASS if not missing else Status.FAIL
    details = f"{len(REQUIRED_FILES) - len(missing)}/{len(REQUIRED_FILES)} обязательных файлов"
    if missing:
        details += f" · отсутствуют: {', '.join(missing)}"
    return result(
        "PROJECT",
        "Project structure",
        status,
        details,
        started=started,
        critical=True,
        remedy="Проверьте наличие всех файлов проекта.",
    )


def check_dependencies() -> CheckResult:
    started = time.perf_counter()
    missing: list[str] = []
    versions: list[str] = []
    for distribution, module in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(module) is None:
            missing.append(distribution)
            continue
        try:
            versions.append(f"{distribution} {importlib.metadata.version(distribution)}")
        except importlib.metadata.PackageNotFoundError:
            versions.append(distribution)
    status = Status.PASS if not missing else Status.FAIL
    details = f"{len(REQUIRED_PACKAGES) - len(missing)}/{len(REQUIRED_PACKAGES)} пакетов"
    if missing:
        details += f" · отсутствуют: {', '.join(missing)}"
    else:
        details += f" · {', '.join(versions[:4])}…"  # <--- ИСПРАВЛЕНО (закрыта скобка)
    return result(
        "PYTHON",
        "Dependencies",
        status,
        details,
        started=started,
        critical=True,
        remedy="python -m pip install -r requirements.txt",
        metrics={"installed": len(REQUIRED_PACKAGES) - len(missing), "required": len(REQUIRED_PACKAGES)},
    )


def project_python_files() -> list[Path]:
    excluded = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    return [
        path for path in ROOT.rglob("*.py")
        if not any(part in excluded for part in path.relative_to(ROOT).parts)
    ]


def check_python_syntax() -> CheckResult:
    started = time.perf_counter()
    files = project_python_files()
    broken: list[str] = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            broken.append(f"{path.relative_to(ROOT)}: {safe_text(exc, 80)}")
    details = f"проверено {len(files)} Python-файлов"
    if broken:
        details += f" · ошибки: {'; '.join(broken[:3])}"
    return result(
        "PYTHON",
        "Source syntax",
        Status.PASS if not broken else Status.FAIL,
        details,
        started=started,
        critical=True,
        remedy="Исправьте синтаксис перечисленных Python-файлов.",
        metrics={"python_files": len(files), "syntax_errors": len(broken)},
    )


def check_core_imports() -> CheckResult:
    started = time.perf_counter()
    broken: list[str] = []
    for module in CORE_MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            broken.append(f"{module}: {type(exc).__name__}: {safe_text(exc, 90)}")
    details = f"{len(CORE_MODULES) - len(broken)}/{len(CORE_MODULES)} основных модулей импортируются"
    if broken:
        details += f" · {'; '.join(broken[:2])}"
    return result(
        "PYTHON",
        "Core module imports",
        Status.PASS if not broken else Status.FAIL,
        details,
        started=started,
        critical=True,
        remedy="Проверьте зависимости и ошибки импорта.",
        metrics={"modules": len(CORE_MODULES), "failed": len(broken)},
    )


def check_env_file() -> CheckResult:
    started = time.perf_counter()
    env_path = ROOT / ".env"
    exists = env_path.is_file()
    return result(
        "CONFIG",
        ".env file",
        Status.PASS if exists else Status.FAIL,
        "локальный файл настроек найден" if exists else "файл .env не найден",
        started=started,
        critical=True,
        remedy="Создайте файл .env на основе .env.example.",
    )


def load_settings(context: DiagnosticContext) -> CheckResult:
    started = time.perf_counter()
    try:
        from app.config import Settings
        context.settings = Settings()
    except Exception as exc:
        return result(
            "CONFIG",
            "Settings parser",
            Status.FAIL,
            f"{type(exc).__name__}: {safe_text(exc)}",
            started=started,
            critical=True,
            remedy="Сверьте значения в .env с .env.example.",
        )
    return result(
        "CONFIG",
        "Settings parser",
        Status.PASS,
        f"окружение={context.settings.app_env} · логирование={context.settings.log_level}",
        started=started,
        critical=True,
    )


def check_credentials(context: DiagnosticContext) -> CheckResult:
    started = time.perf_counter()
    settings = context.settings
    if settings is None:
        return result("CONFIG", "Required credentials", Status.SKIP, "настройки не загружены", started=started, critical=True)

    missing: list[str] = []
    if not settings.bot_token or settings.bot_token == "replace_me":
        missing.append("BOT_TOKEN")
    if not settings.database_url:
        missing.append("DATABASE_URL")

    status = Status.PASS if not missing else Status.FAIL
    details = f"Telegram={mask_secret(settings.bot_token)} · DB={safe_database_label(settings.database_url)}"
    if missing:
        details += f" · не заданы: {', '.join(missing)}"
    return result("CONFIG", "Required credentials", status, details, started=started, critical=True, remedy="Заполните секреты в .env.")


def check_database_url(context: DiagnosticContext) -> CheckResult:
    started = time.perf_counter()
    settings = context.settings
    if settings is None:
        return result("CONFIG", "Database URL", Status.SKIP, "настройки не загружены", started=started, critical=True)
    try:
        from sqlalchemy.engine import make_url
        url = make_url(settings.database_url)
        valid = url.drivername == "postgresql+asyncpg" and bool(url.host and url.database)
        details = f"driver={url.drivername} · host={url.host or '—'} · database={url.database or '—'}"
    except Exception as exc:
        valid = False
        details = f"не удалось разобрать URL: {safe_text(exc)}"
    return result(
        "CONFIG",
        "Database URL",
        Status.PASS if valid else Status.FAIL,
        details,
        started=started,
        critical=True,
        remedy="Используйте postgresql+asyncpg:// в DATABASE_URL.",
    )


def check_storage(context: DiagnosticContext) -> CheckResult:
    started = time.perf_counter()
    storage_root = ROOT / "storage"
    if context.settings is not None:
        configured = Path(context.settings.storage_root)
        storage_root = configured if configured.is_absolute() else ROOT / configured
    try:
        for name in ("uploads", "generated", "cache", "diagnostics", "demo"):
            (storage_root / name).mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(storage_root).free / 1024**3
        status = Status.PASS if free_gb >= 1 else Status.WARN
        details = f"5/5 каталогов доступны · свободно {free_gb:.2f} GB"
    except OSError as exc:
        status = Status.FAIL
        details = f"ошибка записи: {safe_text(exc)}"
    return result("STORAGE", "Local storage", status, details, started=started, critical=True)


def check_project_inventory() -> CheckResult:
    started = time.perf_counter()
    python_count = len(project_python_files())
    migration_count = len(list((ROOT / "alembic" / "versions").glob("*.py")))
    test_count = len(list((ROOT / "tests").glob("test_*.py")))
    demo_images = len(list((ROOT / "storage" / "demo").glob("*.jpg")))
    details = f"🐍 Python: {python_count} · 🧪 тесты: {test_count} · 🗃️ миграции: {migration_count} · 🖼️ demo: {demo_images}"
    return result("PROJECT", "Project inventory", Status.INFO, details, started=started)


def resolve_local_migration_head(context: DiagnosticContext) -> CheckResult:
    started = time.perf_counter()
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        heads = ScriptDirectory.from_config(config).get_heads()
        context.local_revision = ",".join(heads)
        valid = len(heads) == 1
        details = f"head={context.local_revision or 'не найден'}"
    except Exception as exc:
        valid = False
        details = f"{type(exc).__name__}: {safe_text(exc)}"
    return result("DATABASE", "Local Alembic chain", Status.PASS if valid else Status.FAIL, details, started=started, critical=True)


async def check_telegram(context: DiagnosticContext) -> list[CheckResult]:
    started = time.perf_counter()
    if context.offline or not context.settings or not context.settings.bot_token:
        return [result("NETWORK", "Telegram API", Status.SKIP, "проверка пропущена", started=started)]
    try:
        from aiogram import Bot
        bot = Bot(token=context.settings.bot_token)
        try:
            async with asyncio.timeout(context.timeout):
                profile = await bot.get_me()
                context.bot_username = profile.username
        finally:
            await bot.session.close()
        return [result("NETWORK", "Telegram API", Status.PASS, f"@{profile.username} · id={profile.id} · {profile.full_name}", started=started, critical=True)]
    except Exception as exc:
        return [result("NETWORK", "Telegram API", Status.FAIL, f"{type(exc).__name__}: {safe_text(exc)}", started=started, critical=True)]


async def check_database(context: DiagnosticContext) -> list[CheckResult]:
    started = time.perf_counter()
    if context.offline or not context.settings:
        return [result("NETWORK", "Neon PostgreSQL", Status.SKIP, "проверка пропущена", started=started)]
    engine = None
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(context.settings.database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar_one()
            ver = (await conn.execute(text("SHOW server_version"))).scalar_one()
        return [result("NETWORK", "Neon PostgreSQL", Status.PASS, f"database={db} · PostgreSQL {ver} · TLS connected", started=started, critical=True)]
    except Exception as exc:
        return [result("NETWORK", "Neon PostgreSQL", Status.FAIL, f"{type(exc).__name__}: {safe_text(exc)}", started=started, critical=True)]
    finally:
        if engine:
            await engine.dispose()


def run_tool_check(name: str, command: list[str], timeout: float = 180.0) -> CheckResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False
        )
        output = (completed.stdout or completed.stderr).strip().splitlines()
        tail = " · ".join(output[-2:]) if output else "без вывода"
        return result("QUALITY", name, Status.PASS if completed.returncode == 0 else Status.FAIL, f"exit={completed.returncode} · {tail}", started=started)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return result("QUALITY", name, Status.FAIL, f"{type(exc).__name__}: {safe_text(exc)}", started=started)


def skipped_deep_checks() -> list[CheckResult]:
    return [
        CheckResult(section="QUALITY", name="Pytest suite", status=Status.SKIP, details="добавьте --deep для запуска тестов"),
        CheckResult(section="QUALITY", name="Ruff lint", status=Status.SKIP, details="добавьте --deep для проверки кода"),
    ]


def calculate_health(results: list[CheckResult]) -> int:
    scores = {Status.PASS: 100, Status.WARN: 65, Status.FAIL: 0}
    weighted_total = 0
    weight_total = 0
    for item in results:
        if item.status not in scores:
            continue
        weight = 2 if item.critical else 1
        weighted_total += scores[item.status] * weight
        weight_total += weight
    return round(weighted_total / weight_total) if weight_total else 0


class Console:
    def __init__(self, *, clear_screen: bool) -> None:
        self.width = terminal_width()
        self.clear_screen = clear_screen

    def clear(self) -> None:
        if self.clear_screen and sys.stdout.isatty():
            os.system("cls" if os.name == "nt" else "clear")

    def banner(self, context: DiagnosticContext) -> None:
        self.clear()
        print(Theme.paint("═" * self.width, Theme.CYAN))
        print(Theme.paint("FOOD_PORN • ENTERPRISE CONTROL CENTER".center(self.width), Theme.MAGENTA, Theme.BOLD))
        mode = "OFFLINE" if context.offline else "ONLINE"
        depth = "DEEP" if context.deep else "STANDARD"
        print(Theme.paint(f"MODE {mode}  •  SCAN {depth}  •  BUILD {SUPERVISOR_BUILD}".center(self.width), Theme.GRAY))
        print(Theme.paint("═" * self.width, Theme.CYAN))

    def section(self, name: str) -> None:
        print(Theme.paint(f"\n◆ {name}", Theme.BLUE, Theme.BOLD))

    def check(self, item: CheckResult) -> None:
        icon, color = STATUS_STYLE[item.status]
        badge = Theme.paint(f"{icon} {item.status:4}", color, Theme.BOLD)
        print(f"{badge}  {item.name:<30} {Theme.paint(item.details, Theme.WHITE)}")

    def summary(self, results: list[CheckResult], elapsed: float, report_path: Path) -> None:
        score = calculate_health(results)
        fails = sum(1 for r in results if r.critical and r.status == Status.FAIL)
        print()
        print(Theme.paint("╔" + "═" * (self.width - 2) + "╗", Theme.CYAN))
        state = "READY FOR PRODUCTION" if fails == 0 else "ACTION REQUIRED"
        print(Theme.paint("║", Theme.CYAN) + pad(f"  SYSTEM HEALTH: {score}% • {state}", self.width - 2) + Theme.paint("║", Theme.CYAN))
        print(Theme.paint("╚" + "═" * (self.width - 2) + "╝", Theme.CYAN))


async def run_diagnostics(context: DiagnosticContext, console: Console) -> list[CheckResult]:
    results: list[CheckResult] = []
    for fn in (check_python, check_virtual_environment, check_project_structure, check_dependencies, check_python_syntax, check_core_imports, check_env_file):
        item = fn()
        results.append(item)
        console.check(item)

    res = load_settings(context)
    results.append(res)
    console.check(res)

    for fn in (check_credentials, check_database_url, check_storage, resolve_local_migration_head, check_project_inventory):
        item = fn(context) if fn != check_project_inventory else fn()
        results.append(item)
        console.check(item)

    for item in await check_telegram(context):
        results.append(item)
        console.check(item)
    for item in await check_database(context):
        results.append(item)
        console.check(item)

    if context.deep:
        deep_results = [
            run_tool_check("Pytest suite", [sys.executable, "-m", "pytest", "-q"]),
            run_tool_check("Ruff lint", [sys.executable, "-m", "ruff", "check", "."]),
        ]
    else:
        deep_results = skipped_deep_checks()
    for item in deep_results:
        results.append(item)
        console.check(item)

    return results


def write_report(results: list[CheckResult], context: DiagnosticContext, elapsed: float, path: Path) -> None:
    payload = {
        "application": "Food_Porn",
        "generated_at": datetime.now(UTC).isoformat(),
        "health_score": calculate_health(results),
        "results": [asdict(item) for item in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def start_bot(context: DiagnosticContext) -> int:
    print()
    print(Theme.paint("🚀 ЗАПУСК TELEGRAM БОТА", Theme.GREEN, Theme.BOLD))
    if context.bot_username:
        bot_url = f"https://t.me/{context.bot_username}"
        print(f"   🤖 Бот доступен по ссылке: {Theme.link(bot_url, '@' + context.bot_username)}")
    print(Theme.paint("   ⏹ Для остановки нажмите: Ctrl+C", Theme.GRAY))
    print()
    try:
        completed = subprocess.run([sys.executable, "run.py"], cwd=ROOT, check=False)
        return completed.returncode
    except KeyboardInterrupt:
        return 130


def start_admin() -> int:
    print()
    print(Theme.paint("🚀 ЗАПУСК FASTAPI CRM & ADMIN PANEL", Theme.GREEN, Theme.BOLD))
    admin_url = "http://127.0.0.1:8000/admin"
    print(f"   🌐 Админ-панель CRM: {Theme.link(admin_url, admin_url)}")
    print(f"   🔑 Учетные данные:   admin / foodporn_secret")
    print(Theme.paint("   ⏹ Для остановки нажмите: Ctrl+C", Theme.GRAY))
    print()
    try:
        import uvicorn
        uvicorn.run("app.admin_app:app", host="127.0.0.1", port=8000, reload=True)
        return 0
    except Exception as exc:
        print(Theme.paint(f"❌ Ошибка запуска Uvicorn: {exc}", Theme.RED))
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Food_Porn Enterprise Supervisor")
    parser.add_argument("mode", nargs="?", choices=("diagnose", "start", "admin"), default="diagnose")
    parser.add_argument("--offline", action="store_true", help="Без внешних сетевых запросов")
    parser.add_argument("--deep", action="store_true", help="Запустить Pytest и Ruff проверки")
    return parser


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_console(False)

    context = DiagnosticContext(offline=args.offline, deep=args.deep, timeout=8.0)
    console = Console(clear_screen=True)
    console.banner(context)

    started = time.perf_counter()
    results = await run_diagnostics(context, console)
    elapsed = time.perf_counter() - started
    write_report(results, context, elapsed, REPORT_PATH)
    console.summary(results, elapsed, REPORT_PATH)

    if any(r.critical and r.status == Status.FAIL for r in results):
        if args.mode in ("start", "admin"):
            print(Theme.paint("\n⛔ Запуск заблокирован из-за критических ошибок диагностики.", Theme.RED, Theme.BOLD))
            return 2

    if args.mode == "start":
        return start_bot(context)
    elif args.mode == "admin":
        return start_admin()
    return 0


def main() -> int:
    os.chdir(ROOT)
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())