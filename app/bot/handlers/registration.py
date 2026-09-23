"""
==========================================================
FOOD_PORN

Module: Customer Registration Handlers
Layer: Telegram Interface

Responsibilities:
    - Collect name, phone, language, country, and city
    - Validate Telegram contact ownership and phone format
    - Persist the customer and start the first menu
==========================================================
"""

import phonenumbers
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.helpers import item_question
from app.bot.keyboards import REMOVE_KEYBOARD, language_keyboard, phone_keyboard
from app.bot.states import MenuStates, RegistrationStates
from app.database.models import Language
from app.database.repositories import CustomerRepository, MenuRepository
from app.locales.messages import t

router = Router(name="registration")


@router.message(RegistrationStates.name, F.text)
async def receive_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    data = await state.get_data()
    language = data.get("language", "uk")
    if not 2 <= len(name) <= 120:
        await message.answer(t("invalid_title", language))
        return
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.phone)
    await message.answer(t("ask_phone", language), reply_markup=phone_keyboard(language))


@router.message(RegistrationStates.phone, F.contact)
async def receive_phone(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    language = data.get("language", "uk")
    if (
        message.from_user is None
        or message.contact is None
        or message.contact.user_id != message.from_user.id
    ):
        await message.answer(t("wrong_contact", language), reply_markup=phone_keyboard(language))
        return
    try:
        parsed = phonenumbers.parse(message.contact.phone_number, None)
        phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        phone = "+" + message.contact.phone_number.lstrip("+")
    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.language)
    await message.answer(t("ask_language", language), reply_markup=language_keyboard())


@router.message(RegistrationStates.phone)
async def phone_required(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    language = data.get("language", "uk")
    await message.answer(t("wrong_contact", language), reply_markup=phone_keyboard(language))


@router.callback_query(RegistrationStates.language, F.data.startswith("lang:"))
async def select_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = Language(callback.data.split(":", 1)[1])
    await state.update_data(language=language.value)
    await state.set_state(RegistrationStates.country)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t("ask_country", language), reply_markup=REMOVE_KEYBOARD)


@router.message(RegistrationStates.country, F.text)
async def receive_country(message: Message, state: FSMContext) -> None:
    country = (message.text or "").strip()
    data = await state.get_data()
    language = data.get("language", "uk")
    if not 2 <= len(country) <= 120:
        await message.answer(t("invalid_title", language))
        return
    await state.update_data(country=country)
    await state.set_state(RegistrationStates.city)
    await message.answer(t("ask_city", language))


@router.message(RegistrationStates.city, F.text)
async def receive_city(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    city = (message.text or "").strip()
    data = await state.get_data()
    language = Language(data.get("language", "uk"))
    if not 2 <= len(city) <= 120 or message.from_user is None:
        await message.answer(t("invalid_title", language))
        return
    async with session_factory() as session:
        customer = await CustomerRepository(session).register(
            telegram_user_id=message.from_user.id,
            phone=data["phone"],
            name=data["name"],
            language=language,
            country=data["country"],
            city=city,
        )
        menu = await MenuRepository(session).create(customer)
    await state.set_state(MenuStates.item)
    await state.set_data(
        {"menu_id": menu.id, "language": language.value, "category_index": 0, "position": 1}
    )
    await message.answer(
        t("registered", language, name=customer.name),
        reply_markup=REMOVE_KEYBOARD,
    )
    await message.answer(item_question(language, 0, 1))
