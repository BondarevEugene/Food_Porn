"""Archive uploaded gift reference photos before a payment link is offered.

Files are stored under the configured generated/storage root, separately from
the mutable Telegram upload staging folder. Railway needs a persistent volume
for STORAGE_ROOT; this helper cannot make ephemeral disks durable on its own.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from app.config import Settings
from app.services.replicate_vision_board import ReplicateVisionBoardRenderer


def stage_paid_gift_photos(
    settings: Settings,
    *,
    user_id: int,
    uploads: list[str | Path],
) -> list[Path]:
    """Normalize and archive 1..7 local, owner-scoped photos idempotently."""
    if user_id < 1 or not 1 <= len(uploads) <= 7:
        raise ValueError("Expected 1 to 7 photos for a valid Telegram user")
    allowed = (settings.uploads_dir / "wallpapers" / str(user_id)).resolve()
    digest = hashlib.sha256(str(user_id).encode())
    sources = []
    for item in uploads:
        photo = Path(item).resolve()
        if not photo.is_file() or not photo.is_relative_to(allowed):
            raise ValueError("Photo does not belong to this gift upload")
        digest.update(photo.name.encode())
        with photo.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        sources.append(photo)
    output = (
        settings.generated_dir / "gift_sources"
        / str(user_id) / digest.hexdigest()[:32]
    )
    output.mkdir(parents=True, exist_ok=True)
    archived = []
    for index, source in enumerate(sources, 1):
        destination = output / f"source_{index}.jpg"
        if not destination.is_file():
            temporary = output / f".{destination.name}.{uuid.uuid4().hex}.tmp"
            try:
                ReplicateVisionBoardRenderer._prepare_photo(source, temporary)
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    raise ValueError("Photo archival produced no output")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        archived.append(destination)
    return archived
