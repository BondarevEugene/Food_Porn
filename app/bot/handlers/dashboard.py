"""
==========================================================
FOOD_PORN

Module: Menu Dashboard Handlers
Layer: Interface
==========================================================
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.markdown import hblockquote, hbold
from app.bot.keyboards.dashboard import MenuAction, build_menu_dashboard_kb

from app.database.repositories import MenuRepository

router = Router()


def format_premium_dashboard(menu) -> str:
    """
    Формирует лаконичный и дорогой текст предпросмотра меню.
    Использует классическую лингвистику и блочные цитаты для эстетики.
    """
    status_indicator = "⚫️ Формирование" if menu.status == "draft" else "⚜️ В обработке"

    lines = [
        hbold(f"Гастрономический сет #{menu.id}"),
        f"Статус: {status_indicator}",
        ""
    ]

    if not menu.items:
        lines.append(hblockquote("Сет пока пуст. Добавьте первую позицию для начала работы."))
    else:
        lines.append(hbold("Утвержденные подачи:"))
        for idx, item in enumerate(menu.items, start=1):
            category_icon = "🍽" if item.category == "main" else "🍷" if item.category == "drink" else "🥗"
            lines.append(hblockquote(f"{idx}. {category_icon} {item.title}"))

    lines.extend([
        "",
        "В сет автоматически будут включены:",
        "▪️ Индивидуальные рецепты от шефа",
        "▪️ Консолидированный лист закупок",
        "▪️ Стилизованные иллюстрации подач"
    ])

    return "\n".join(lines)


@router.callback_query(MenuAction.filter(F.action == "view_dashboard"))
async def show_dashboard(callback: CallbackQuery, callback_data: MenuAction, session_factory):
    """Отображает или обновляет главный пульт управления меню."""
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)

    if not menu:
        await callback.answer("Сет не найден.", show_alert=True)
        return

    text = format_premium_dashboard(menu)
    # Если есть хотя бы одно блюдо, разрешаем генерацию
    can_generate = len(menu.items) > 0
    kb = build_menu_dashboard_kb(menu.id, can_generate)

    # Бесшовное обновление интерфейса
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "generate_pdf"))
async def trigger_generation(callback: CallbackQuery, callback_data: MenuAction, session_factory):
    """Запускает процесс сборки и блокирует интерфейс от лишних нажатий."""
    # Заглушка: здесь будет вызов background-воркера
    await callback.message.edit_text(
        hbold("⚜️ Процесс запущен.\n\n") +
        hblockquote(
            "Нейросети формируют визуальный стиль, собирают рецептуру и верстают финальный документ. Ожидайте готовности."),
        parse_mode="HTML"
    )
    await callback.answer("Генерация начата", show_alert=False)
