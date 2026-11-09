"""Restore missing customer photos from Telegram before AI generation."""

import logging
from pathlib import Path

from app.services.storage import StorageService

logger = logging.getLogger(__name__)


async def restore_missing_menu_photos(menu, bot, settings, repo) -> None:
    """Re-download missing photos and persist paths; never re-download valid files."""
    storage = StorageService(settings)
    for role in ("cover", "spread"):
        path_field = f"{role}_photo_path"
        file_id_field = f"{role}_telegram_file_id"
        current_path = getattr(menu, path_field, None)
        if current_path and Path(current_path).is_file():
            continue
        file_id = getattr(menu, file_id_field, None)
        if not file_id:
            raise RuntimeError(
                f"Missing {role} photo for menu {menu.id}; customer must upload it again"
            )
        try:
            recovered = await storage.save_telegram_photo(
                bot, file_id, menu_id=menu.id, role=role
            )
        except Exception as exc:
            logger.warning("Telegram photo restore failed for menu %s (%s)", menu.id, role)
            raise RuntimeError(
                f"Could not restore {role} photo for menu {menu.id}; request reupload"
            ) from exc
        await repo.set_photos(menu.id, **{role: str(recovered)})
        setattr(menu, path_field, str(recovered))
