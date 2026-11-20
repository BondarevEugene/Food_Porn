"""Telegram Little Legend mode chooser contract tests."""
from pathlib import Path

SOURCE = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_mode_chooser_exposes_all_three_modes():
    for callback in ("ll_mode:director", "ll_mode:classic", "ll_mode:brief"):
        assert 'f"ll_mode:{mode}"' in SOURCE
        assert callback.split(":")[1] in SOURCE


def test_new_modes_do_not_claim_live_editor():
    assert 'if mode == "director" and studio_url:' in SOURCE
    assert 'callback_data="ll_choose_mode"' in SOURCE


def test_navigation_has_back_to_products():
    assert 'callback_data="prod_little_legend"' in SOURCE
    assert 'callback_data="back_to_products"' in SOURCE
