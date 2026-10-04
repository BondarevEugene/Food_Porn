"""Collect source files and migrations to prepare a patch for a local checkout.

Run from the Food_Porn project root: python collect_food_porn_sources.py
The zip excludes .env, .venv, storage, uploaded photos and generated images.
"""
from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path.cwd()
DESTINATION = ROOT / "Food_Porn_sources_for_merge.zip"
SOURCE_FOLDERS = ("app", "alembic", "tests")
CONFIG_FILES = (
    "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    "README.md", "Dockerfile", "docker-compose.yml", "alembic.ini",
)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ("git", *args), cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout


def redact_embedded_tokens(data: bytes) -> bytes:
    """Strip obvious live credentials embedded in Python source before sharing."""
    data = re.sub(rb"r8_[A-Za-z0-9]{12,}", b"REDACTED_REPLICATE_TOKEN", data)
    data = re.sub(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}", b"REDACTED_OPENAI_KEY", data)
    return data


def main() -> None:
    if not (ROOT / ".git").exists() or not (ROOT / "app").is_dir():
        raise SystemExit("Run this script from the Food_Porn repository root.")

    files = sorted(
        {path for folder in SOURCE_FOLDERS for path in (ROOT / folder).rglob("*.py")
         if path.is_file() and "__pycache__" not in path.parts}
        | {path for path in ROOT.glob("*.py") if path.is_file() and path.name != Path(__file__).name}
        | {ROOT / name for name in CONFIG_FILES if (ROOT / name).is_file()}
    )
    with zipfile.ZipFile(DESTINATION, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("_git_head.txt", git_output("rev-parse", "HEAD"))
        archive.writestr("_git_status.txt", git_output("status", "--short"))
        for path in files:
            archive.writestr(path.relative_to(ROOT).as_posix(), redact_embedded_tokens(path.read_bytes()))

    print(f"Created {DESTINATION.name} ({len(files)} files). Upload this ZIP to the chat.")


if __name__ == "__main__":
    main()
