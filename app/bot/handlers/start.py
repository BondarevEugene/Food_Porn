"""
==========================================================
FOOD_PORN

Module: Start and Navigation Handlers
Layer: Telegram Interface

Responsibilities:
    - Process `/start`, `/help`, and `/cancel`
    - Restore the registered customer main menu
    - Handle unsupported Telegram messages
==========================================================
"""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import REMOVE_KEYBOARD, main_keyboard
from app.database.models import Language
from app.database.repositories import CustomerRepository
from app.locales.messages import t

router = Router(name="start")


def telegram_language(code: str | None) -> Language:
    if code and code.lower().startswith("ru"):
        return Language.RU
    if code and code.lower().startswith("en"):
        return Language.EN
    return Language.UK


@router.message(CommandStart())
async def start_command(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    async with session_factory() as session:
        repo = CustomerRepository(session)
        customer = await repo.by_telegram_id(message.from_user.id)
        if customer:
            await repo.touch(customer)
            await message.answer(
                t("welcome_back", customer.language, name=customer.name),
                reply_markup=main_keyboard(customer.language),
            )
            return

    language = telegram_language(message.from_user.language_code)
    await state.set_state("RegistrationStates:name")
    await state.update_data(language=language.value)
    await message.answer(t("welcome", language), reply_markup=REMOVE_KEYBOARD)


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    language = data.get("language", telegram_language(message.from_user.language_code if message.from_user else None))
    await state.clear()
    await message.answer(t("cancelled", language), reply_markup=REMOVE_KEYBOARD)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Food_Porn\n\n/start — start or open the main menu\n/cancel — cancel current input\n/new — create a menu",
        reply_markup=REMOVE_KEYBOARD,
    )
