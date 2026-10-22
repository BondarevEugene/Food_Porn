"""Apply the OpenAI error-handling update with guarded patches and rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent


def normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def candidates(root: Path):
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    changes = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Unsafe manifest path")
        source = BUNDLE / "payload" / relative
        target = root / relative
        if not target.resolve().is_relative_to(
            root
        ) or not source.resolve().is_relative_to(BUNDLE):
            raise RuntimeError("Unsafe path: " + str(relative))
        desired = normalized(source)
        if hashlib.sha256(desired.encode()).hexdigest() != entry["new_hash"]:
            raise RuntimeError("Payload checksum mismatch: " + str(relative))
        current = normalized(target) if target.exists() else None
        if current == desired:
            continue
        if entry["mode"] == "new":
            if current is not None:
                raise RuntimeError(
                    "Existing file differs: " + str(relative) + ". No files changed."
                )
        else:
            if current is None:
                raise RuntimeError(
                    "Required source missing: " + str(relative) + ". No files changed."
                )
            updated = current
            for hunk in entry["hunks"]:
                if (
                    updated.count(hunk["before"]) == 0
                    and updated.count(hunk["after"]) == 1
                ):
                    continue
                if updated.count(hunk["before"]) != 1:
                    raise RuntimeError(
                        "Cannot safely patch "
                        + str(relative)
                        + ". No files changed; send this source file for adaptation."
                    )
                updated = updated.replace(hunk["before"], hunk["after"], 1)
            desired = updated
        if relative.suffix == ".py":
            compile(desired, str(relative), "exec")
        if current != desired:
            changes.append((relative, desired))
    return changes


def require_stopped(root: Path):
    from dotenv import dotenv_values

    values = dotenv_values(root / ".env")
    port = int(os.environ.get("MINIAPP_PORT") or values.get("MINIAPP_PORT") or 8080)
    try:
        connection = socket.create_connection(("127.0.0.1", port), timeout=0.3)
    except OSError:
        return
    connection.close()
    raise RuntimeError(f"Stop launcher.py / bot on port {port} before installing.")


def restore(root: Path, backup: Path, records):
    for entry in reversed(records):
        target = root / entry["path"]
        if entry["existed"]:
            shutil.copy2(backup / entry["path"], target)
        elif target.exists():
            target.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Install; otherwise preview only"
    )
    parser.add_argument("--project", type=Path, default=BUNDLE.parent)
    args = parser.parse_args()
    root = args.project.resolve()
    if sys.version_info < (3, 11):  # noqa: UP036 -- installer may be run with an older Python
        raise RuntimeError(
            "Python 3.11+ is required; use the project virtual environment."
        )
    if (
        not (root / "launcher.py").is_file()
        or not (root / "app/crm/security.py").is_file()
    ):
        raise RuntimeError(
            "Place _openai_errors_update_1_0 beside launcher.py after installing Mini CRM."
        )
    changes = candidates(root)
    for relative, _ in changes:
        print("UPDATE", relative, flush=True)
    if not args.apply:
        print(f"{len(changes)} file(s). Run with --apply to install.")
        return
    if not changes:
        print("OpenAI error-handling update already installed.")
        return
    require_stopped(root)
    backup = root / ("_openai_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup.mkdir()
    records = []
    for relative, _ in changes:
        target = root / relative
        records.append({"path": relative.as_posix(), "existed": target.exists()})
        if target.exists():
            stored = backup / relative
            stored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, stored)
    (backup / "restore.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    try:
        for relative, content in changes:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            if relative.suffix == ".py":
                py_compile.compile(str(target), doraise=True)
        environment = os.environ.copy()
        environment.update(
            BOT_TOKEN="123:test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            OPENAI_API_KEY="test",
            ADMIN_TELEGRAM_IDS="",
            FREE_GENERATION_TELEGRAM_IDS="",
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=root,
            env=environment,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Pytest exited with code {result.returncode}; details are shown above."
            )
    except BaseException:
        restore(root, backup, records)
        print(
            "Installation failed. Source files restored. Backup:",
            backup.name,
            flush=True,
        )
        raise
    print("OpenAI error-handling update installed. Backup:", backup.name)
    print("Start: python launcher.py start")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", str(exc))
        raise SystemExit(1) from None
