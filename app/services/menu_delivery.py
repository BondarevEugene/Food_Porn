"""Resolve already generated paid-menu files without invoking AI or billing."""

from pathlib import Path

from app.database.models import FileKind, Menu


class MenuDeliveryUnavailable(ValueError):
    """The paid order has no complete, readable delivery package."""


def paid_menu_documents(menu: Menu) -> tuple[Path, Path]:
    """Return existing print PDF and recipe PDF, or reject incomplete orders."""
    if not menu.is_paid:
        raise MenuDeliveryUnavailable("Order is not paid")

    by_kind = {file.kind: Path(file.path) for file in menu.files}
    documents: list[Path] = []
    for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET):
        path = by_kind.get(kind)
        if path is None or not path.is_file():
            raise MenuDeliveryUnavailable(f"Generated document missing: {kind.value}")
        try:
            if path.stat().st_size < 1024:
                raise MenuDeliveryUnavailable(f"Generated document is empty: {kind.value}")
            with path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise MenuDeliveryUnavailable(f"Invalid PDF document: {kind.value}")
        except OSError as exc:
            raise MenuDeliveryUnavailable(f"Generated document unreadable: {kind.value}") from exc
        documents.append(path)
    return documents[0], documents[1]
