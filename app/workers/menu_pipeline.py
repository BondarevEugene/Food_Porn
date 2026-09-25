"""
==========================================================
FOOD_PORN

Module: Menu Processing Pipeline
Layer: Worker / Background Task

Responsibilities:
    - Execute background generation of images, recipes, and shopping lists
    - Manage async booklet rendering via BookletRenderer
    - Deliver preview artwork and payment invoices or VIP clean files via Telegram
==========================================================
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import get_payment_keyboard
from app.config import Settings
from app.database.models import FileKind, GenerationStatus, MenuStatus
from app.database.repositories import MenuRepository
from app.render.booklet import BookletRenderer
from app.services.image_generation import ImageGenerationService
from app.services.payment import PaymentService
from app.services.printshop import PrintshopService
from app.services.prompt_builder import PromptBuilder
from app.services.recipe_generator import RecipeGeneratorService
from app.services.shopping import aggregate_shopping_list

logger = logging.getLogger(__name__)


class MenuPipeline:
    def __init__(self, bot, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.bot = bot
        self.settings = settings
        self.session_factory = session_factory
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

        self.image_service = ImageGenerationService(settings)
        self.prompt_builder = PromptBuilder()
        self.recipe_service = RecipeGeneratorService(settings)
        self.renderer = BookletRenderer(settings.generated_dir)
        self.payment_service = PaymentService(settings)
        self.printshop_service = PrintshopService(settings)

    async def start(self) -> None:
        """Запускает фоновые воркеры обработки меню."""
        logger.info("Menu pipeline worker pool starting...")
        for _ in range(self.settings.image_concurrency):
            task = asyncio.create_task(self._worker())
            self._tasks.append(task)

    async def stop(self) -> None:
        """Корректно останавливает фоновые воркеры."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.image_service.close()
        logger.info("Menu pipeline worker pool stopped.")

    async def submit(self, menu_id: int, telegram_user_id: int) -> bool:
        """Ставит сет в очередь на обработку."""
        logger.info(f"Menu ID:{menu_id} enqueued for processing by user {telegram_user_id}.")
        await self.queue.put(menu_id)
        return True

    async def retry(self, menu_id: int, telegram_user_id: int) -> bool:
        return await self.submit(menu_id, telegram_user_id)

    async def _worker(self) -> None:
        while True:
            try:
                menu_id = await self.queue.get()
                await self._process(menu_id)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Critical worker failure: {exc}", exc_info=True)

    async def _process(self, menu_id: int) -> None:
        logger.info(f"Pipeline execution started for Menu ID:{menu_id}")
        async with self.session_factory() as session:
            repo = MenuRepository(session)
            menu = await repo.get(menu_id, full=True)

            if not menu:
                logger.error(f"Menu ID:{menu_id} not found in database.")
                return

            try:
                # Шаг 1: Генерация изображений блюд с защитой от дублирования
                for item in menu.items:
                    if item.generation_status == GenerationStatus.DONE and item.image_path:
                        continue

                    prompt = self.prompt_builder.build(item)
                    await repo.set_item_processing(item, prompt)

                    destination = self.settings.uploads_dir / str(menu.id) / f"item_{item.id}.jpg"
                    try:
                        path = await self.image_service.generate(prompt, destination)
                        await repo.set_item_done(item, str(path))
                    except Exception as img_exc:
                        logger.error(f"Image generation failed for item {item.id}: {img_exc}")
                        await repo.set_item_failed(item, str(img_exc))

                # Шаг 2: Генерация рецептов через LLM или локальный фоллбэк
                language = getattr(menu.customer, "language", "uk") or "uk"
                dish_titles = [item.title for item in menu.items]
                menu_details = await self.recipe_service.generate_menu_details(dish_titles, language)

                # Шаг 3: Агрегация списка покупок
                shopping_list = aggregate_shopping_list(menu_details)
                shopping_text = self._format_shopping_list(shopping_list, language)

                # Шаг 4: Рендеринг через штатный метод BookletRenderer
                rendered_artifacts = await asyncio.to_thread(self.renderer.render, menu)
                preview_image_path = rendered_artifacts.outside_preview
                production_pdf_path = rendered_artifacts.print_pdf

                logger.info(f"Render artifacts created successfully -> Outside preview: {preview_image_path}")

                # Получение chat_id и идентификации пользователя
                chat_id = getattr(menu.customer, "telegram_user_id", None) or getattr(menu.customer, "chat_id", None)
                if not chat_id and menu.customer:
                    chat_id = getattr(menu.customer, "id", None)

                # Проверка на VIP-пользователей (@bondarev_e / @Voloshka0602 или ваш Telegram ID)
                customer_telegram_id = getattr(menu.customer, "telegram_user_id", 0)
                # Укажите здесь ваш реальный Telegram ID или проверяйте по нику/флагу
                VIP_IDS = {725003786}  # Ваш ID из предыдущих логов воркера
                is_vip = customer_telegram_id in VIP_IDS

                is_uk = str(language).lower() in ("uk", "ukrainian")

                if is_vip:
                    # ВИП-режим: сразу отмечаем как оплаченное и выдаем чистые файлы без эквайринга
                    await repo.mark_as_paid(menu_id, payment_id=f"VIP_PASS_{menu_id}", payment_system="vip_bypass")

                    if preview_image_path and Path(preview_image_path).exists() and chat_id:
                        vip_msg = (
                            "👑 <b>VIP-доступ активовано для @bondarev_e / @Voloshka0602!</b>\n\n"
                            "Оплата для цього акаунта пропущена автоматично. Завантажуємо чистий буклет..."
                            if is_uk else
                            "👑 <b>VIP-доступ активирован!</b>\n\n"
                            "Оплата для вашего акаунта пропущена автоматически. Загружаем чистый буклет..."
                        )
                        await self.bot.send_message(chat_id=chat_id, text=vip_msg, parse_mode="HTML")

                        # Отправляем чистый PDF без водяных знаков
                        if production_pdf_path and Path(production_pdf_path).exists():
                            caption_prod = "🎉 <b>Ваш офіційний гастрономічний сет (VIP чиста версія):</b>" if is_uk else "🎉 <b>Ваш официальный гастрономический сет (VIP чистая версия):</b>"
                            await self.bot.send_document(
                                chat_id=chat_id,
                                document=FSInputFile(str(production_pdf_path)),
                                caption=caption_prod,
                                parse_mode="HTML"
                            )

                        # Автоматическая отправка в типографию
                        if production_pdf_path and Path(production_pdf_path).exists():
                            customer_info = f"VIP User ID: {customer_telegram_id}"
                            success_dispatch = await self.printshop_service.dispatch_to_printshop(menu_id, Path(production_pdf_path), customer_info)
                            if success_dispatch:
                                await repo.mark_sent_to_printshop(menu_id)
                                print_msg = "🖨 <i>VIP-замовлення автоматично передано до друкарні!</i>" if is_uk else "🖨 <i>VIP-заказ автоматически передано в типографию!</i>"
                                await self.bot.send_message(chat_id=chat_id, text=print_msg, parse_mode="HTML")

                        await self.bot.send_message(chat_id=chat_id, text=shopping_text, parse_mode="HTML")

                    await repo.set_status(menu_id, MenuStatus.COMPLETED)
                    logger.info(f"VIP Pipeline successfully finished for Menu ID:{menu_id}")
                    return

                # Стандартный коммерческий режим для остальных пользователей
                price = self.settings.menu_price
                currency = self.settings.currency
                portmone_link = self.payment_service.create_portmone_invoice(menu.id, price, f"Menu #{menu.id}")
                redsys_link = self.payment_service.create_redsys_invoice(menu.id, price / 42.0, f"Menu #{menu.id}")
                pay_keyboard = get_payment_keyboard(menu.id, portmone_link, redsys_link, language)

                if preview_image_path and Path(preview_image_path).exists() and chat_id:
                    try:
                        file_kind = getattr(FileKind, "PREVIEW", None) or list(FileKind)[0]
                        await repo.save_file(menu.id, file_kind, str(preview_image_path))
                    except Exception as db_file_exc:
                        logger.warning(f"Non-critical DB file save warning: {db_file_exc}")

                    caption = (
                        f"✨ <b>Ваш превью-гастрономічний сет #{menu.id} готовий!</b>\n\n"
                        f"🔒 <i>На превью нанесені захисні водяні знаки.</i>\n"
                        f"💰 <b>Вартість повного комплекту:</b> {price} {currency}\n\n"
                        f"Після оплати ви миттєво отримаєте чистий буклет і замовлення відправиться в друкарню!"
                        if is_uk else
                        f"✨ <b>Ваш превью-гастрономический сет #{menu.id} готов!</b>\n\n"
                        f"🔒 <i>На превью нанесены защитные водяные знаки.</i>\n"
                        f"💰 <b>Стоимость полного комплекта:</b> {price} {currency}\n\n"
                        f"После оплаты вы получите чистый буклет, а заказ уйдет в типографию!"
                    )

                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=FSInputFile(str(preview_image_path)),
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=pay_keyboard
                    )

                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=shopping_text,
                        parse_mode="HTML"
                    )

                await repo.set_status(menu_id, MenuStatus.COMPLETED)
                logger.info(f"Pipeline successfully finished for Menu ID:{menu_id}")

            except Exception as proc_exc:
                logger.error(f"Pipeline processing failed for Menu ID:{menu_id}: {proc_exc}", exc_info=True)
                await repo.set_status(menu_id, MenuStatus.FAILED, error_message=str(proc_exc))

    @staticmethod
    def _format_shopping_list(shopping_list: dict | list, language: str) -> str:
        is_uk = str(language).lower() in ("uk", "ukrainian")
        shop_title = "🛒 <b>Список необхідних продуктів:</b>" if is_uk else "🛒 <b>Список необходимых продуктов:</b>"
        lines = [shop_title]

        if isinstance(shopping_list, dict):
            for category, items in shopping_list.items():
                lines.append(f"\n<b>{category}</b>")
                for item in items:
                    lines.append(f"• {item}")
        elif isinstance(shopping_list, list):
            for item in shopping_list:
                lines.append(f"• {item}")

        return "\n".join(lines)
