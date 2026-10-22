"""Install Mini CRM with backups, guarded text patches and regression checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent


def text_bytes(data: bytes) -> str:
    return data.decode("utf-8-sig").replace("\r\n", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def candidates(root: Path):
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    changes = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Unsafe manifest path")
        source = BUNDLE / "payload" / relative
        desired = text_bytes(source.read_bytes())
        if digest(desired) != entry["new_hash"]:
            raise RuntimeError(f"Payload hash mismatch: {relative}")
        target = root / relative
        if not target.resolve().is_relative_to(root):
            raise RuntimeError(f"Path outside project: {relative}")
        current = text_bytes(target.read_bytes()) if target.exists() else None
        if current == desired:
            continue
        if entry["mode"] == "patch" and current is not None:
            updated = current
            for hunk in entry["hunks"]:
                if (
                    updated.count(hunk["before"]) == 0
                    and updated.count(hunk["after"]) == 1
                ):
                    continue
                if updated.count(hunk["before"]) != 1:
                    raise RuntimeError(
                        f"Cannot safely patch {relative}. Your local version differs. No files changed; send this file for adaptation."
                    )
                updated = updated.replace(hunk["before"], hunk["after"], 1)
            desired = updated
        elif entry["mode"] == "new" and current is not None:
            raise RuntimeError(
                f"File already exists with different content: {relative}. No files changed."
            )
        elif entry["mode"] == "patch" and current is None:
            raise RuntimeError(f"Required source file missing: {relative}")
        changes.append((relative, desired))
    return changes


def stop_running_bot(root: Path):
    from dotenv import dotenv_values

    values = dotenv_values(root / ".env")
    value = os.environ.get("MINIAPP_PORT") or values.get("MINIAPP_PORT") or "8080"
    try:
        port = int(value)
        connection = socket.create_connection(("127.0.0.1", port), timeout=0.3)
    except OSError:
        return
    connection.close()
    raise RuntimeError(f"Stop the bot / web server on port {port} before installing.")


def ensure_private_settings(root: Path):
    import secrets

    from cryptography.fernet import Fernet
    from dotenv import dotenv_values

    env_file = root / ".env"
    values = dotenv_values(env_file)
    additions = []
    encryption_key = os.environ.get("CRM_ENCRYPTION_KEY") or values.get(
        "CRM_ENCRYPTION_KEY"
    )
    if encryption_key:
        Fernet(encryption_key.encode())  # Never replace a configured encryption key.
    else:
        additions.append("CRM_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
    if not (
        os.environ.get("ADMIN_SESSION_SECRET") or values.get("ADMIN_SESSION_SECRET")
    ):
        additions.append("ADMIN_SESSION_SECRET=" + secrets.token_urlsafe(48))
    if additions:
        with env_file.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n# Mini CRM private settings; keep these values in backups.\n"
                + "\n".join(additions)
                + "\n"
            )
    if os.name != "nt":
        env_file.chmod(0o600)


def initialize_database(root: Path):
    code = """import asyncio
from app.config import get_settings
from app.crm.models import initialize_schema
from app.database.session import engine
async def setup():
    try:
        await initialize_schema(engine)
    finally:
        await engine.dispose()
try:
    asyncio.run(setup())
except Exception as exc:
    print("CRM schema initialization failed: " + type(exc).__name__)
    raise SystemExit(1)
"""
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)


def rollback(root: Path, backup: Path, records: list[dict]):
    for item in reversed(records):
        target = root / item["path"]
        stored = backup / item["path"]
        if item["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stored, target)
        elif target.exists():
            target.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Install; default is a read-only preview"
    )
    parser.add_argument("--project", type=Path, default=BUNDLE.parent)
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Advanced: dependencies already installed",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Advanced: omit pytest after installation",
    )
    args = parser.parse_args()
    root = args.project.resolve()
    if sys.version_info < (3, 11):
        raise RuntimeError(
            "Python 3.11+ required; use your project virtual environment."
        )
    if (
        not (root / "app" / "miniapp" / "api.py").is_file()
        or not (root / "launcher.py").is_file()
    ):
        raise RuntimeError("Extract _crm_update_1_0 into the Food_Porn project root.")
    changes = candidates(root)
    for relative, _ in changes:
        print("UPDATE", relative)
    if not args.apply:
        print(f"{len(changes)} file(s). Run again with --apply to install.")
        return
    stop_running_bot(root)
    if not args.skip_deps:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "cryptography>=44,<51",
                "itsdangerous>=2.2,<3",
                "aiosqlite>=0.20,<1",
            ],
            check=True,
        )
    backup = root / ("_crm_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup.mkdir()
    records = []
    for relative in [*[relative for relative, _ in changes], Path(".env")]:
        target = root / relative
        entry = {"path": relative.as_posix(), "existed": target.exists()}
        records.append(entry)
        if target.exists():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
    (backup / "restore.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    try:
        for relative, content in changes:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        ensure_private_settings(root)
        # Compile the exact candidate files, without scanning update/backup folders.
        import py_compile

        for relative, _ in changes:
            if relative.suffix == ".py":
                py_compile.compile(str(root / relative), doraise=True)
        initialize_database(root)
        if not args.skip_tests:
            environment = os.environ.copy()
            environment.update(
                BOT_TOKEN="123:test",
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                OPENAI_API_KEY="test",
                ADMIN_TELEGRAM_IDS="",
                FREE_GENERATION_TELEGRAM_IDS="",
            )
            subprocess.run(
                [sys.executable, "-m", "pytest", "tests", "-q"],
                cwd=root,
                env=environment,
                check=True,
            )
    except BaseException:
        rollback(root, backup, records)
        print(f"Installation failed. Files restored. Backup: {backup.name}")
        print(
            "New empty CRM tables, if created, are retained; existing bot tables and Alembic revisions were not changed."
        )
        raise
    print(f"Mini CRM installed. Backup: {backup.name}")
    print(
        "Start: python launcher.py start; Telegram: /start -> Mini CRM; browser: /crm after /admin/login."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", str(exc))
        raise SystemExit(1) from None
