"""Order dashboard must not offer generation while payment or fulfillment is active."""
from types import SimpleNamespace

import pytest

from app.bot.handlers.menu import build_dashboard_kb, format_premium_dashboard
from app.database.models import MenuStatus


def _menu(status):
    return SimpleNamespace(
        id=101,
        meal_period="full_day",
        status=status,
        customer=SimpleNamespace(language="ru"),
        is_paid=status in (MenuStatus.PAID, MenuStatus.SENT_TO_PRINTSHOP, MenuStatus.COMPLETED),
        items=[SimpleNamespace(title="Суп")],
        cover_photo_path="cover.jpg",
        spread_photo_path="spread.jpg",
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (MenuStatus.QUEUED, "поставлено в очередь"),
        (MenuStatus.IMAGES_READY, "Иллюстрации готовы"),
        (MenuStatus.WAITING_FOR_PAYMENT, "Перейдите к оплате"),
        (MenuStatus.PAID, "Оплата подтверждена"),
        (MenuStatus.SENT_TO_PRINTSHOP, "передан в типографию"),
        (MenuStatus.COMPLETED, "Меню создано"),
        (MenuStatus.PARTIAL_SUCCESS, "Часть файлов готова"),
        (MenuStatus.FAILED, "Создание не удалось"),
    ],
)
def test_dashboard_explains_actual_order_state(status, expected):
    menu = _menu(status)
    assert expected in format_premium_dashboard(menu)
    callbacks = [
        button.callback_data or ""
        for row in build_dashboard_kb(menu).inline_keyboard
        for button in row
    ]
    if status != MenuStatus.FAILED:
        assert not any("generate" in value for value in callbacks)


def test_draft_remains_generatable():
    menu = _menu(MenuStatus.DRAFT)
    assert any(
        "generate" in (button.callback_data or "")
        for row in build_dashboard_kb(menu).inline_keyboard
        for button in row
    )
