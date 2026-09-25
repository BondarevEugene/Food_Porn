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


def get_payment_keyboard(menu_id: int, portmone_url: str, redsys_url: str, language: str = "uk") -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру с выбором эквайринга и кнопкой проверки статуса оплаты."""
    is_uk = language.lower() in ("uk", "ukrainian")

    portmone_text = "💳 Оплатити через Portmone (UAH)" if is_uk else "💳 Оплатить через Portmone (UAH)"
    redsys_text = "🌍 Pay with Redsys (Cards / EUR)" if is_uk else "🌍 Pay with Redsys (Cards / EUR)"
    check_text = "🔄 Перевірити оплату" if is_uk else "🔄 Проверить оплату"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=portmone_text, url=portmone_url),
            ],
            [
                InlineKeyboardButton(text=redsys_text, url=redsys_url),
            ],
            [
                InlineKeyboardButton(text=check_text, callback_data=f"check_payment_{menu_id}"),
            ],
        ]
    )