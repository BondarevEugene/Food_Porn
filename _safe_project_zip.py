
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Food_Porn_SAFE_AUDIT.zip"

# Exclude directories containing environments, credentials,
# local databases, caches and generated customer content.
EXCLUDED_DIRS = {
    ".git", ".github", ".idea", ".venv", ".venv312", "venv",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".tox", "node_modules", "dist", "build", "logs", "storage",
    "uploads", "media", "generated", "outputs", "private",
    "secrets", "credentials", "backups", "tmp", "temp",
    ".next", ".cache",
}

# Files that must never enter the archive.
EXCLUDED_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    ".env.test", ".env.staging", ".envrc",
    "credentials.json", "service-account.json",
    "service_account.json", "token.json",
    "secrets.json", "secrets.yaml", "secrets.yml",
    "id_rsa", "id_ed25519", "known_hosts",
    ".npmrc", ".pypirc", ".netrc",
}

EXCLUDED_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".pem", ".key",
    ".p12", ".pfx", ".p8", ".jks", ".keystore",
    ".zip", ".7z", ".rar", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".mp4", ".mov", ".pdf", ".mp3", ".wav",
    ".log", ".bak", ".dump", ".backup",
}

# Allowlist: archive source code and useful project metadata only.
ALLOWED_SUFFIXES = {
    ".py", ".toml", ".ini", ".cfg", ".md", ".txt",
    ".html", ".css", ".js", ".ts", ".json",
    ".yaml", ".yml", ".sql", ".jinja", ".j2",
}

ALLOWED_SPECIAL = {
    "Dockerfile", "Procfile", ".gitignore",
    ".dockerignore", "Makefile",
}

# Exclude files whose names indicate sensitive content.
SENSITIVE_FILENAME = re.compile(
    r"(secret|credential|private[_-]?key|"
    r"service[_-]?account|token[_-]?backup|"
    r"customer[_-]?export|user[_-]?export)",
    re.IGNORECASE,
)

# Detect common credential assignments and token formats.
SENSITIVE_CONTENT = re.compile(
    r"""(?ix)
    (?:api[_-]?key|secret[_-]?key|bot[_-]?token|
       database[_-]?url|password|merchant[_-]?secret|
       access[_-]?token|refresh[_-]?token)
    \s*[:=]\s*
    ["']?(?!none\b|null\b|replace_me\b|changeme\b|
           your[_-]|example\b|test\b)
    [A-Za-z0-9_:/@.+\-]{12,}
    |
    sk-[A-Za-z0-9_-]{20,}
    |
    \b\d{7,12}:[A-Za-z0-9_-]{30,}\b
    |
    -----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----
    """,
)

def is_allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts

    if any(part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
        return False

    name = path.name.lower()

    if name.startswith(".env") or name in EXCLUDED_NAMES:
        return False

    if SENSITIVE_FILENAME.search(name):
        return False

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False

    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        if path.name not in ALLOWED_SPECIAL:
            return False

    # Avoid large files and accidental data dumps.
    if path.stat().st_size > 1_000_000:
        return False

    return True


def main() -> None:
    included = []
    skipped_sensitive = []
    skipped_other = 0

    with zipfile.ZipFile(
        OUTPUT, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for directory, dirs, files in os.walk(ROOT):
            dirs[:] = [
                name for name in dirs
                if name.lower() not in EXCLUDED_DIRS
                and not name.startswith(".")
            ]

            for filename in files:
                path = Path(directory) / filename

                if path == OUTPUT or path.is_symlink():
                    continue

                if not is_allowed(path):
                    skipped_other += 1
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeError, OSError):
                    skipped_other += 1
                    continue

                if SENSITIVE_CONTENT.search(content):
                    skipped_sensitive.append(
                        str(path.relative_to(ROOT))
                    )
                    continue

                archive.writestr(
                    path.relative_to(ROOT).as_posix(),
                    content,
                )
                included.append(str(path.relative_to(ROOT)))

    print("=" * 60)
    print("FOOD_PORN SAFE PROJECT EXPORT")
    print("=" * 60)
    print(f"Included files: {len(included)}")
    print(f"Skipped other files: {skipped_other}")
    print(f"Skipped potentially sensitive: {len(skipped_sensitive)}")
    print(f"Archive: {OUTPUT}")

    if skipped_sensitive:
        print("\nFiles excluded due to possible secrets:")
        for name in skipped_sensitive:
            print(" -", name)

    print("\nIMPORTANT:")
    print("Review the archive before sharing.")
    print("Automatic secret detection is not a guarantee.")


if __name__ == "__main__":
    main()
