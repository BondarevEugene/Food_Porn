"""Paid-menu delivery uses existing PDFs and never invokes image generation."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bot.handlers.menu import build_dashboard_kb
from app.database.models import FileKind, MenuStatus
from app.services.menu_delivery import MenuDeliveryUnavailable, paid_menu_documents


def _pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n" + b" " * 1024)
    return path


def _menu(tmp_path: Path, *, paid: bool = True, missing: bool = False):
    booklet = _pdf(tmp_path / "booklet.pdf")
    recipes = tmp_path / "recipes.pdf"
    if not missing:
        _pdf(recipes)
    return SimpleNamespace(
        id=92,
        is_paid=paid,
        status=MenuStatus.PARTIAL_SUCCESS,
        files=[
            SimpleNamespace(kind=FileKind.PRINT_PDF, path=str(booklet)),
            SimpleNamespace(kind=FileKind.RECIPE_SHEET, path=str(recipes)),
        ],
        items=[],
        cover_photo_path=None,
        spread_photo_path=None,
    )


def test_paid_menu_documents_reuse_existing_files(tmp_path: Path) -> None:
    menu = _menu(tmp_path)
    booklet, recipes = paid_menu_documents(menu)
    assert booklet.name == "booklet.pdf"
    assert recipes.name == "recipes.pdf"


def test_unpaid_menu_cannot_resend(tmp_path: Path) -> None:
    with pytest.raises(MenuDeliveryUnavailable, match="not paid"):
        paid_menu_documents(_menu(tmp_path, paid=False))


def test_missing_recipe_blocks_incomplete_resend(tmp_path: Path) -> None:
    with pytest.raises(MenuDeliveryUnavailable, match="missing"):
        paid_menu_documents(_menu(tmp_path, missing=True))


def test_corrupt_pdf_blocks_resend(tmp_path: Path) -> None:
    menu = _menu(tmp_path)
    Path(menu.files[0].path).write_bytes(b"invalid" * 200)
    with pytest.raises(MenuDeliveryUnavailable, match="Invalid PDF"):
        paid_menu_documents(menu)


def test_paid_menu_dashboard_offers_resend(tmp_path: Path) -> None:
    markup = build_dashboard_kb(_menu(tmp_path))
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any("resend" in value for value in callbacks)


def test_unpaid_menu_dashboard_hides_resend(tmp_path: Path) -> None:
    markup = build_dashboard_kb(_menu(tmp_path, paid=False))
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert not any("resend" in value for value in callbacks)
