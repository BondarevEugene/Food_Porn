"""Conservative disk-budget cleanup for disposable generation scratch files.

Never traverse uploads, customer assets, or paid-order output directories.
A separate scheduler can call cleanup_scratch once per six hours.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    examined: int
    deleted: int
    reclaimed_bytes: int


def cleanup_scratch(
    storage_root: Path, *, max_age_hours: int = 24, dry_run: bool = True,
    now: float | None = None,
) -> CleanupResult:
    """Remove old regular files ONLY from storage/cache/gift_scratch.

    No symlinks are followed. Directory deletion is deliberately unsupported.
    A running renderer must not place active work here without an age lease.
    """
    if max_age_hours < 6:
        raise ValueError("Minimum scratch retention is six hours")
    root = Path(storage_root)
    scratch = root / "cache" / "gift_scratch"
    if not root.is_absolute() or root.is_symlink() or scratch.is_symlink():
        raise ValueError("Unsafe storage root")
    if not scratch.is_dir():
        return CleanupResult(0, 0, 0)
    cutoff = (time.time() if now is None else now) - max_age_hours * 3600
    examined = deleted = reclaimed = 0
    for entry in scratch.iterdir():
        if entry.is_symlink() or not entry.is_file():
            continue
        examined += 1
        try:
            stat = entry.stat(follow_symlinks=False)
            if stat.st_mtime >= cutoff:
                continue
            if not dry_run:
                entry.unlink()
            deleted += 1
            reclaimed += stat.st_size
        except OSError:
            logger.exception("Could not inspect or delete scratch file %s", entry.name)
    return CleanupResult(examined, deleted, reclaimed)


def storage_pressure(storage_root: Path) -> int:
    """Percentage of disk space used, for metrics and admission control."""
    root = Path(storage_root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Storage root must exist and be absolute")
    total, used, _ = shutil.disk_usage(root)
    return round(100 * used / total) if total else 100
