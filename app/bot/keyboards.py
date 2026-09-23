"""
==========================================================
FOOD_PORN

Module: Keyboards
Layer: Presentation
==========================================================
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

# Универсальный инструмент для очистки чата от старых кнопок
REMOVE_KEYBOARD = ReplyKeyboardRemove()


def main_keyboard(language: str = "uk") -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


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
