"""Telegram palette flow has bounded callbacks and no accidental mass-choice screen."""
from types import SimpleNamespace

from app.bot.handlers.little_legend_palettes import _keyboard, _parse
from app.little_legend.palette_catalog import book_palette_catalog


def test_picker_only_shows_five_colors_at_a_time() -> None:
    catalog = book_palette_catalog()
    assert len(catalog.groups) == 3
    for group in catalog.groups:
        buttons = _keyboard([
            (option.title, f"ll_pconfirm:42:{option.id}")
            for option in group.options
        ])
        assert len(buttons.inline_keyboard) == 5
        assert all(len(row) == 1 for row in buttons.inline_keyboard)
        assert all(len(row[0].callback_data) <= 64
                   for row in buttons.inline_keyboard)


def test_picker_rejects_other_chats_and_malformed_ids() -> None:
    def callback(data: str, chat_id: int = 42, kind: str = "private"):
        return SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id, type=kind)),
        )

    assert _parse(callback("ll_palette:5"), 2) == ["ll_palette", "5"]
    assert _parse(callback("ll_palette:0"), 2) is None
    assert _parse(callback("ll_palette:-1"), 2) is None
    assert _parse(callback("ll_palette:no"), 2) is None
    assert _parse(callback("ll_palette:5", chat_id=43), 2) is None
    assert _parse(callback("ll_palette:5", kind="group"), 2) is None
    assert _parse(callback("ll_palette:5:extra"), 2) is None
