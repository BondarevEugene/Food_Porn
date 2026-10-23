"""Telegram administration backed by the same queries and rights as Mini CRM."""

from __future__ import annotations

import re
from html import escape

from aiogram import BaseMiddleware, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import get_settings
from app.crm import service
from app.database import async_session_maker
from app.services.admin_access import crm_url, has_admin_access
from app.services.settings_service import get_paid_test_user_ids

router = Router(name="admin")


class AdminOnly(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if user is None:
            return None
        if not await has_admin_access(
            user.id, getattr(user, "username", None), get_settings(), async_session_maker
        ):
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа к админке.", show_alert=True)
            else:
                await event.answer("Нет доступа к админке.")
            return None
        message = event.message if isinstance(event, CallbackQuery) else event
        chat = getattr(message, "chat", None)
        if chat is not None and getattr(chat, "type", "private") != "private":
            await event.answer("Откройте админку в личном чате с ботом.")
            return None
        return await handler(event, data)


router.message.middleware(AdminOnly())
router.callback_query.middleware(AdminOnly())


class AdminStates(StatesGroup):
    waiting_for_value = State()
    waiting_for_vip_username = State()


VIP_USERNAME_RE = re.compile(r"@?[A-Za-z0-9_]{5,32}")


def is_owner(user_id: int) -> bool:
    """Only stable numeric owner IDs may change the VIP composition."""
    return user_id in get_settings().admin_telegram_ids


async def require_owner(callback: CallbackQuery) -> bool:
    if is_owner(callback.from_user.id):
        return True
    await callback.answer(
        "Изменять VIP может только владелец из ADMIN_TELEGRAM_IDS.",
        show_alert=True,
    )
    return False


def normalize_vip_username(value: str) -> str:
    """Return a canonical Telegram username or raise a user-facing error."""
    candidate = value.strip().split()[0] if value.strip() else ""
    if candidate.startswith("https://t.me/"):
        candidate = candidate.removeprefix("https://t.me/").split("/", 1)[0]
    candidate = candidate.lstrip("@").casefold()
    if not VIP_USERNAME_RE.fullmatch(candidate):
        raise ValueError("Введите Telegram username: 5–32 латинских букв, цифр или _. Например: @voloshka0602")
    return candidate


async def save_vip_list(names: list[str], actor_id: int, action: str) -> list[str]:
    """Persist a canonical, deduplicated VIP list and its audit record."""
    normalized = list(
        dict.fromkeys(name.strip().lstrip("@").casefold() for name in names if name.strip())
    )
    async with async_session_maker() as session:
        from app.database.models import AppSetting

        row = await session.get(AppSetting, "vip_usernames")
        before = row.value.split(",") if row and row.value else []
        if row:
            row.value = ",".join(normalized)
        else:
            session.add(
                AppSetting(
                    key="vip_usernames",
                    value=",".join(normalized),
                    description="Telegram usernames with free product access",
                )
            )
        service.audit(
            session,
            f"telegram:{actor_id}",
            action,
            {"before": before, "after": normalized},
        )
        await session.commit()
    return normalized


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    rows = []
    url = crm_url(get_settings())
    if url:
        rows.append([InlineKeyboardButton(text="✦ Открыть Mini CRM", web_app=WebAppInfo(url=url))])
    rows.extend(
        [
            [
                InlineKeyboardButton(text="📊 Обзор", callback_data="admin_stats"),
                InlineKeyboardButton(text="👥 Клиенты", callback_data="admin_customers"),
            ],
            [
                InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders"),
                InlineKeyboardButton(text="💳 Финансы", callback_data="admin_finance"),
            ],
            [
                InlineKeyboardButton(text="📣 Реклама", callback_data="admin_ads"),
                InlineKeyboardButton(text="⚙️ Цены и VIP", callback_data="admin_settings"),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Админка", callback_data="admin_home")]]
    )


def settings_keyboard(
    data: dict,
    *,
    owner: bool,
    paid_test_active: bool = False,
) -> InlineKeyboardMarkup:
    labels = {
        "menu_price_uah": "Меню · UAH",
        "menu_price_stars": "Меню · Stars",
        "gift_price_stars": "Подарок · Stars",
        "usd_exchange_rate": "Курс USD / UAH",
    }
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{label}: {data['values'][key]}",
                callback_data=f"admin_value:{key}",
            )
        ]
        for key, label in labels.items()
    ]
    if owner:
        buttons.extend(
            [
                [
                    InlineKeyboardButton(text="➕ Добавить VIP", callback_data="admin_vip_add"),
                    InlineKeyboardButton(text="➖ Удалить VIP", callback_data="admin_vip_remove"),
                ],
                [
                    InlineKeyboardButton(
                        text=(
                            "👑 Вернуть мне VIP-доступ"
                            if paid_test_active
                            else "🧪 Проверить оплату от себя"
                        ),
                        callback_data="admin_paid_test_toggle",
                    )
                ],
            ]
        )
    buttons.append([InlineKeyboardButton(text="← Админка", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_text(data: dict, *, owner: bool, paid_test_active: bool = False) -> str:
    access_note = (
        (
            "\n\n🧪 <b>Ваш платный тест включён.</b> Следующий новый заказ потребует оплату. "
            "Админка остаётся доступна. После проверки нажмите «Вернуть мне VIP-доступ»."
            if paid_test_active
            else "\n\n<b>Проверка оплаты:</b> кнопка ниже временно отключит бесплатную выдачу "
            "только для вашего Telegram ID. Состав VIP при этом не изменится."
        )
        if owner
        else "\n\nИзменять VIP может только владелец из ADMIN_TELEGRAM_IDS."
    )
    return (
        "⚙️ <b>Цены и доступ</b>\n\nVIP-логины: "
        + escape(", ".join(f"@{name.lstrip('@')}" for name in data["vip"]) or "нет")
        + "\n\nЦены Stars используются для новых счетов. Уже выставленные счета сохраняют свою цену."
        "\nДля подарков цена UAH рассчитывается по фактической стоимости API + 5%."
        + access_note
    )


async def show_settings(target: Message, *, owner_id: int | None, edit: bool) -> None:
    async with async_session_maker() as session:
        data = await service.crm_settings(session)
        paid_test_active = bool(
            owner_id is not None and owner_id in await get_paid_test_user_ids(session)
        )
    method = target.edit_text if edit else target.answer
    await method(
        settings_text(
            data,
            owner=owner_id is not None,
            paid_test_active=paid_test_active,
        ),
        reply_markup=settings_keyboard(
            data,
            owner=owner_id is not None,
            paid_test_active=paid_test_active,
        ),
        parse_mode="HTML",
    )


async def summary_text() -> str:
    async with async_session_maker() as session:
        stats = await service.dashboard(session, 30)
    return (
        f"✦ <b>Food_Porn · Mini CRM</b>\nЗа последние 30 дней\n\n"
        f"👥 Активных клиентов: <b>{stats['customers']}</b> · всего в базе: <b>{stats['customers_total']}</b>\n"
        f"📦 Реальных заказов: <b>{stats['qualified_orders']}</b> · всех попыток: <b>{stats['orders']}</b>\n"
        f"💼 Коммерческих возможностей: <b>{stats['commercial_opportunities']}</b> · оплат: <b>{stats['paid_orders']}</b>\n"
        f"👑 Бесплатных VIP-заказов: <b>{stats['vip_orders']}</b>\n"
        f"💳 Выручка: <b>{stats['revenue_uah']} UAH</b> и <b>{stats['revenue_stars']} ⭐</b>\n"
        f"🤖 OpenAI: <b>{stats['ai_costs']['effective_uah']} UAH</b> "
        f"({stats['ai_costs']['operations']} операций; {stats['ai_costs']['source']})\n"
        f"📉 Все расходы: <b>{stats['expenses_total_uah']} UAH</b>\n"
        f"📊 Коммерческая конверсия: <b>{stats['conversion']}%</b>\n\n"
        "Заказы считаются по дате создания, выручка — по дате оплаты. "
        "VIP и черновики исключены из коммерческой конверсии."
    )


@router.message(F.text.in_({"/admin", "👑 Админка", "✦ Mini CRM"}))
async def admin_panel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        await summary_text(), reply_markup=get_admin_main_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"admin_home", "admin_stats", "admin_finance"}))
async def admin_home_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        await summary_text(), reply_markup=get_admin_main_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_customers")
async def customers(callback: CallbackQuery):
    await callback.answer()
    async with async_session_maker() as session:
        data = await service.customers_page(session, limit=8)
    lines = [f"👥 <b>Клиенты · {data['total']}</b>\n"]
    for row in data["items"]:
        lines.append(
            f"<b>{escape(row['name'] or 'Telegram-клиент')}</b> · <code>{row['telegram_id']}</code>\n"
            f"Заказы: {row['orders']}, коммерческие оплаты: {row['paid_orders']}"
        )
    lines.append("\nПоиск, заметки и экспорт доступны в Mini CRM.")
    await callback.message.edit_text(
        "\n\n".join(lines), reply_markup=get_admin_main_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_orders")
async def orders(callback: CallbackQuery):
    await callback.answer()
    async with async_session_maker() as session:
        data = await service.orders_page(session, limit=8)
    lines = [f"📦 <b>Заказы за 30 дней · {data['total']}</b>\n"]
    for row in data["items"]:
        amount = (
            f"{row['stars'] or 0} ⭐" if row["payment_kind"] == "stars" else f"{row['amount']} UAH"
        )
        lines.append(
            f"{'Меню' if row['product'] == 'menu' else 'Подарок'} #{row['id']} · {escape(row['status'])}\n"
            f"{amount} · {escape(row['payment_kind'])}"
        )
    await callback.message.edit_text(
        "\n\n".join(lines), reply_markup=get_admin_main_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_ads")
async def advertising(callback: CallbackQuery):
    from sqlalchemy import select

    from app.crm.models import Integration

    await callback.answer()
    async with async_session_maker() as session:
        rows = (await session.execute(select(Integration))).scalars().all()
    lines = ["📣 <b>Рекламные интеграции</b>\n"]
    for provider, name in [("meta", "Meta · Facebook / Instagram"), ("google_ads", "Google Ads")]:
        row = next((item for item in rows if item.provider == provider), None)
        lines.append(f"{name}: <b>{escape(row.status if row else 'не настроено')}</b>")
    lines.append(
        "\nНастройка аккаунтов и безопасное хранение ключей, проверка подключения и отчёты по кампаниям — в Mini CRM."
    )
    await callback.message.edit_text(
        "\n\n".join(lines), reply_markup=get_admin_main_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await show_settings(
        callback.message,
        owner_id=callback.from_user.id if is_owner(callback.from_user.id) else None,
        edit=True,
    )


@router.callback_query(F.data == "admin_paid_test_toggle")
async def toggle_paid_test(callback: CallbackQuery):
    if not await require_owner(callback):
        return
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        from app.database.models import AppSetting

        current = await get_paid_test_user_ids(session)
        enabled = user_id not in current
        if enabled:
            current.add(user_id)
        else:
            current.discard(user_id)
        value = ",".join(str(item) for item in sorted(current))
        row = await session.get(AppSetting, "paid_test_telegram_ids")
        if row:
            row.value = value
        else:
            session.add(
                AppSetting(
                    key="paid_test_telegram_ids",
                    value=value,
                    description="Owner IDs temporarily testing commercial checkout",
                )
            )
        service.audit(
            session,
            f"telegram:{user_id}",
            "access.paid_test.toggle",
            {"telegram_id": user_id, "enabled": enabled},
        )
        await session.commit()
    await callback.answer(
        "Платный тест включён." if enabled else "VIP-доступ возвращён.",
        show_alert=True,
    )
    await show_settings(callback.message, owner_id=user_id, edit=True)


@router.callback_query(F.data == "admin_vip_add")
async def prompt_vip_add(callback: CallbackQuery, state: FSMContext):
    if not await require_owner(callback):
        return
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_vip_username)
    await callback.message.edit_text(
        "➕ <b>Добавление VIP</b>\n\n"
        "Отправьте Telegram username пользователя. Можно написать "
        "<code>@username</code>, <code>username</code> или ссылку "
        "<code>https://t.me/username</code>.\n\n"
        "После добавления пользователь получит бесплатную генерацию и доступ к CRM.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="← Цены и VIP", callback_data="admin_settings")]
            ]
        ),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_vip_username, F.text)
async def add_vip(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        await message.answer("Изменять VIP может только владелец из ADMIN_TELEGRAM_IDS.")
        return
    try:
        username = normalize_vip_username(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    async with async_session_maker() as session:
        data = await service.crm_settings(session)
    existing = {name.lstrip("@").casefold() for name in data["vip"]}
    if username in existing:
        await message.answer(f"@{username} уже входит в VIP.")
    else:
        await save_vip_list(
            [*data["vip"], username],
            message.from_user.id,
            "access.vip.add",
        )
        await message.answer(f"✅ @{username} добавлен в VIP.")
    await state.clear()
    await show_settings(message, owner_id=message.from_user.id, edit=False)


@router.callback_query(F.data == "admin_vip_remove")
async def choose_vip_remove(callback: CallbackQuery):
    if not await require_owner(callback):
        return
    await callback.answer()
    async with async_session_maker() as session:
        data = await service.crm_settings(session)
    buttons = [
        [
            InlineKeyboardButton(
                text=f"❌ @{name.lstrip('@')}",
                callback_data=f"admin_vip_delete:{name.lstrip('@').casefold()}",
            )
        ]
        for name in data["vip"]
    ]
    buttons.append([InlineKeyboardButton(text="← Цены и VIP", callback_data="admin_settings")])
    await callback.message.edit_text(
        "➖ <b>Удаление VIP</b>\n\n"
        "Нажмите на пользователя. Бесплатный доступ отключится сразу; "
        "его завершённые заказы и файлы не удаляются.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_vip_delete:"))
async def delete_vip(callback: CallbackQuery):
    if not await require_owner(callback):
        return
    username = callback.data.removeprefix("admin_vip_delete:").casefold()
    async with async_session_maker() as session:
        data = await service.crm_settings(session)
    names = [name for name in data["vip"] if name.lstrip("@").casefold() != username]
    if len(names) == len(data["vip"]):
        await callback.answer("Пользователь уже удалён из VIP.", show_alert=True)
        return
    await save_vip_list(names, callback.from_user.id, "access.vip.remove")
    await callback.answer(f"@{username} удалён из VIP.", show_alert=True)
    await show_settings(callback.message, owner_id=callback.from_user.id, edit=True)


@router.callback_query(F.data.startswith("admin_value:"))
async def prompt_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.removeprefix("admin_value:")
    if key not in service.SETTING_RULES:
        await callback.answer("Неизвестный параметр", show_alert=True)
        return
    await callback.answer()
    await state.update_data(crm_setting_key=key)
    await state.set_state(AdminStates.waiting_for_value)
    low, high, _, _ = service.SETTING_RULES[key]
    await callback.message.edit_text(
        f"Введите новое значение для <code>{escape(key)}</code> ({low}–{high}).",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_value, F.text)
async def save_setting(message: Message, state: FSMContext):
    key = (await state.get_data()).get("crm_setting_key")
    try:
        async with async_session_maker() as session:
            await service.save_settings(
                session, {key: message.text.strip()}, f"telegram:{message.from_user.id}"
            )
    except (ValueError, ArithmeticError) as exc:
        await message.answer(escape(str(exc)), parse_mode="HTML")
        return
    await state.clear()
    await message.answer(
        "Настройка сохранена и применяется к новым заказам.", reply_markup=get_admin_main_keyboard()
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Вернуться в мастерскую: /start")
