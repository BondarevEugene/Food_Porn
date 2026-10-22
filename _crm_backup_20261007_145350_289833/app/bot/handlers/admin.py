"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Admin Panel Handlers (Interactive Telegram Control)
==========================================================
"""

from aiogram import BaseMiddleware, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.database import async_session_maker
from app.services.payment import PaymentService
from app.services.settings_service import (
    get_collage_price,
    set_setting,
)

router = Router(name="admin")


class AdminOnly(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if user is None:
            return None

        settings = get_settings()
        # Проверяем доступ по ID администратора или по списку VIP/админских username
        is_admin = (
            user.id in settings.admin_telegram_ids or
            (user.username and user.username in settings.default_vip_users)
        )

        if not is_admin:
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ лише для адміністратора.", show_alert=True)
            else:
                await event.answer("Доступ лише для адміністратора.")
            return None

        return await handler(event, data)


router.message.middleware(AdminOnly())
router.callback_query.middleware(AdminOnly())


class AdminStates(StatesGroup):
    waiting_for_price = State()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Змінити ціну колажу", callback_data="admin_set_price")],
            [InlineKeyboardButton(text="📊 Статистика системи", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main")],
        ]
    )


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в адмін-панель", callback_data="admin_home")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main")],
        ]
    )


@router.message(F.text == "/admin")
async def admin_panel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session_maker() as session:
        price = await get_collage_price(session)

    text = (
        "👑 <b>Панель керування екосистемою</b>\n\n"
        f"💰 Поточна ціна колажу: <b>{price} UAH</b>\n"
        "Оберіть необхідну дію нижче:"
    )
    await message.answer(text, reply_markup=get_admin_main_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_home")
async def admin_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session_maker() as session:
        price = await get_collage_price(session)

    text = (
        "👑 <b>Панель керування екосистемою</b>\n\n"
        f"💰 Поточна ціна колажу: <b>{price} UAH</b>\n"
        "Оберіть необхідну дію нижче:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_main_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_set_price")
async def admin_set_price_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_for_price)
    text = (
        "💰 <b>Введіть нову ціну колажу у гривнях (UAH):</b>\n\n"
        "Наприклад: <i>500</i> або <i>750</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_for_price, F.text)
async def admin_save_price(message: Message, state: FSMContext) -> None:
    try:
        new_price = int(message.text.strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Будь ласка, введіть коректне число (ціну у грн). Спробуйте ще раз:")
        return

    async with async_session_maker() as session:
        await set_setting(session, "collage_price_uah", str(new_price))

    await state.clear()
    text = f"✅ <b>Успішно!</b> Нова ціна колажу встановлена: <b>{new_price} UAH</b>."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В адмін-панель", callback_data="admin_home")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main")],
        ]
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    payment_ready = PaymentService(get_settings()).portmone_ready
    text = (
        "📊 <b>Системна статистика</b>\n\n"
        f"• Portmone: {'налаштовано' if payment_ready else 'не налаштовано'}\n"
        "• Колаж: локальна композиція з ваших фотографій"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "🏠 Ви повернулися до головного меню. Натисніть /start або скористайтеся кнопками знизу."
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

# Добавьте в AdminStates в admin.py:
class AdminStates(StatesGroup):
    waiting_for_price = State()
    waiting_for_broadcast_text = State()  # Ожидание текста рассылки


# Добавьте кнопку в клавиатуру админки get_admin_main_keyboard():
[InlineKeyboardButton(text="📢 Сделать рассылку (Broadcast)", callback_data="admin_broadcast_menu")]


# Добавьте обработчики:
@router.callback_query(F.data == "admin_broadcast_menu")
async def admin_broadcast_menu(callback: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Всем клиентам", callback_data="bc_seg_all")],
            [InlineKeyboardButton(text="🛒 Брошенные корзины (Неоплаченные)", callback_data="bc_seg_unpaid")],
            [InlineKeyboardButton(text="💎 Только с оплаченными заказами", callback_data="bc_seg_paid")],
            [InlineKeyboardButton(text="🔙 Назад в админ-панель", callback_data="admin_home")],
        ]
    )
    text = "📢 <b>Центр рассылок и сегментации</b>\n\nВыберите целевую аудиторию для отправки сообщения:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("bc_seg_"))
async def admin_start_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    segment = callback.data.replace("bc_seg_", "")
    await state.update_data(broadcast_segment=segment)
    await state.set_state(AdminStates.waiting_for_broadcast_text)

    text = (
        f"✍️ <b>Введите текст рассылки для сегмента: <code>{segment}</code></b>\n\n"
        "Сообщение будет отправлено всем пользователям выбранной категории. Поддерживается HTML-разметка."
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast_text, F.text)
async def admin_send_broadcast(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    segment = data.get("broadcast_segment", "all")
    broadcast_text = message.text

    await state.clear()
    processing_msg = await message.answer("⏳ <b>Запуск рассылки...</b>", parse_mode="HTML")

    async with async_session_maker() as session:
        bot = message.bot
        success, fail = await execute_broadcast(bot, session, broadcast_text, segment)

    result_text = (
        f"✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"• Сегмент: <code>{segment}</code>\n"
        f"• Успешно доставлено: <b>{success}</b>\n"
        f"• Ошибок / заблокировали бота: <b>{fail}</b>"
    )
    await processing_msg.edit_text(result_text, reply_markup=get_admin_main_keyboard(), parse_mode="HTML")
