"""
==========================================================
FOOD_PORN

Module: Keyboards
Layer: Presentation
==========================================================
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# Универсальный инструмент для очистки чата от старых кнопок
REMOVE_KEYBOARD = ReplyKeyboardRemove()


def main_keyboard(language: str = "uk") -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру главного меню."""
    is_uk = str(language).lower() in ("uk", "ukrainian")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍝 Створити гастрономічний сет" if is_uk else "🍝 Создать гастрономический сет",
                    callback_data="start_menu_flow"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✨ Створити шпалери-маніфестацію" if is_uk else "✨ Создать обои-манифестацию",
                    callback_data="start_wallpaper_flow"
                )
            ],
        ]
    )


def review_keyboard(language: str = "uk") -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def language_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для выбора языка при регистрации."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇺🇦 Українська"), KeyboardButton(text="🇷🇺 Русский")],
            [KeyboardButton(text="🇬🇧 English")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def phone_keyboard(language: str = "uk") -> ReplyKeyboardMarkup:
    """Клавиатура для обязательного запроса номера телефона."""
    btn_text = "📱 Поділитися контактом" if language == "uk" else "📱 Поделиться контактом"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn_text, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_payment_keyboard(
    menu_id: int,
    invoice_url: str,
    language: str = "uk",
    *,
    provider: str = "telegram_stars",
    amount: str | None = None,
) -> InlineKeyboardMarkup:
    """Checkout and server-verification controls for the digital order."""
    is_uk = language.lower() in ("uk", "ukrainian")
    if provider == "mono":
        payment_text = "💳 Оплатити карткою" if is_uk else "💳 Оплатить картой"
    elif provider == "portmone":
        payment_text = "💳 Оплатити Portmone" if is_uk else "💳 Оплатить Portmone"
    else:
        payment_text = "⭐ Оплатити Stars" if is_uk else "⭐ Оплатить Stars"
    if amount:
        payment_text = f"{payment_text} · {amount} UAH"
    check_text = "🔄 Перевірити оплату" if is_uk else "🔄 Проверить оплату"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=payment_text, url=invoice_url),
            ],
            [
                InlineKeyboardButton(text=check_text, callback_data=f"check_payment_{menu_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_products")],
        ]
    )


def add_wayforpay_option(
    keyboard: InlineKeyboardMarkup | None,
    *,
    product: str,
    reference_id: int,
    payment_id: int,
    checkout_url: str,
    amount: str,
    language: str = "uk",
    test_mode: bool = False,
) -> InlineKeyboardMarkup:
    """Add an independent WayForPay choice without replacing another provider."""
    lang = str(language).lower()
    if lang in {"uk", "ukrainian"}:
        pay = "💳 Оплатити карткою · WayForPay"
        check = "✅ Я оплатив · перевірити WayForPay"
        test = "🧪 ТЕСТ · "
        back = "⬅️ Назад"
    elif lang in {"en", "english"}:
        pay = "💳 Pay by card · WayForPay"
        check = "✅ I paid · check WayForPay"
        test = "🧪 TEST · "
        back = "⬅️ Back"
    else:
        pay = "💳 Оплатить картой · WayForPay"
        check = "✅ Я оплатил · проверить WayForPay"
        test = "🧪 ТЕСТ · "
        back = "⬅️ Назад"
    rows = [list(row) for row in (keyboard.inline_keyboard if keyboard else [])]
    back_row = None
    if rows and any(button.callback_data == "back_to_products" for button in rows[-1]):
        back_row = rows.pop()
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"{test if test_mode else ''}{pay} · {amount} UAH",
                    url=checkout_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text=check,
                    callback_data=f"check_wayforpay:{payment_id}",
                )
            ],
        ]
    )
    rows.append(back_row or [InlineKeyboardButton(text=back, callback_data="back_to_products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
