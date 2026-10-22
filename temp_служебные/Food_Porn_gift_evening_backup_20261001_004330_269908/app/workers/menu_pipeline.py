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
import hashlib
import logging
from decimal import Decimal
from pathlib import Path

from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import get_payment_keyboard
from app.config import Settings
from app.database.models import FileKind, GenerationStatus, MenuStatus
from app.database.repositories import MenuRepository
from app.render.booklet import BookletRenderer
from app.render.recipes import render_recipe_sheet
from app.services.free_access import has_free_generation_access
from app.services.image_generation import ImageGenerationService
from app.services.menu_quality import validate_menu_artwork, validate_menu_files
from app.services.prompt_builder import PromptBuilder
from app.services.recipe_generator import RecipeGeneratorService
from app.services.settings_service import get_setting
from app.services.shopping import aggregate_shopping_list
from app.services.stars import OrderRef, create_invoice

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
                if self.settings.use_mock_images:
                    raise RuntimeError("USE_MOCK_IMAGES=true: настоящие фотографии отключены. Установите false в .env")
                customer_telegram_id = menu.customer.telegram_user_id
                username = None
                if customer_telegram_id not in (
                    *self.settings.admin_telegram_ids, *self.settings.free_generation_telegram_ids,
                ):
                    try:
                        chat = await self.bot.get_chat(customer_telegram_id)
                        username = getattr(chat, "username", None)
                    except Exception:
                        logger.warning("Could not look up username for menu customer %s", customer_telegram_id)
                is_vip = await has_free_generation_access(
                    customer_telegram_id, username, self.settings, self.session_factory)
                placeholder = self.settings.demo_dir / "placeholder.jpg"
                mock_hash = hashlib.sha256(placeholder.read_bytes()).digest() if placeholder.is_file() else None
                # Шаг 1: Генерация изображений блюд с защитой от дублирования
                for item in menu.items:
                    if item.title == "—":
                        continue
                    ready = item.generation_status == GenerationStatus.DONE and item.image_path and Path(item.image_path).is_file()
                    if ready and mock_hash is not None:
                        ready = hashlib.sha256(Path(item.image_path).read_bytes()).digest() != mock_hash
                    if ready:
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

                failed_titles = [item.title for item in menu.items if item.title != "—" and
                                 (item.generation_status != GenerationStatus.DONE or not item.image_path
                                  or not Path(item.image_path).is_file())]
                if failed_titles:
                    raise RuntimeError(f"Menu images are incomplete: {', '.join(failed_titles[:3])}")
                validate_menu_artwork(menu, placeholder)

                # Шаг 2: Генерация рецептов через LLM или локальный фоллбэк
                language = getattr(menu.customer, "language", "uk") or "uk"
                dish_titles = [item.title for item in menu.items if item.title != "—"]
                menu_details = await self.recipe_service.generate_menu_details(dish_titles, language)

                # Шаг 3: Агрегация списка покупок
                shopping_list = aggregate_shopping_list(menu_details)
                shopping_text = self._format_shopping_list(shopping_list, language)

                # Рецепты и список продуктов выдаются вместе с оплаченным PDF.
                rendered_artifacts = await asyncio.to_thread(self.renderer.render, menu)
                preview_image_path = rendered_artifacts.outside_preview
                production_pdf_path = rendered_artifacts.print_pdf
                recipe_path = await asyncio.to_thread(
                    render_recipe_sheet,
                    self.settings.generated_dir / str(menu.id) / f"food_porn_recipe_sheet_{menu.id}.pdf",
                    menu_details,
                    shopping_list,
                    str(language),
                )
                validate_menu_files(menu, (production_pdf_path, recipe_path,
                                           rendered_artifacts.inside_preview,
                                           rendered_artifacts.outside_preview), menu_details)
                for kind, path in rendered_artifacts.as_mapping().items():
                    await repo.save_file(menu.id, kind, str(path))
                await repo.save_file(menu.id, FileKind.RECIPE_SHEET, str(recipe_path))

                logger.info(f"Render artifacts created successfully -> Outside preview: {preview_image_path}")

                # Получение chat_id и идентификации пользователя
                chat_id = menu.customer.telegram_user_id

                is_uk = str(language).lower() in ("uk", "ukrainian")

                if is_vip or menu.is_paid:
                    # ВИП-режим: сразу отмечаем как оплаченное и выдаем чистые файлы без эквайринга
                    if not menu.is_paid:
                        await repo.mark_as_paid(menu_id, payment_id=f"VIP_PASS_{menu_id}", payment_system="vip_bypass")

                    if preview_image_path and Path(preview_image_path).exists() and chat_id:
                        vip_msg = (
                            "👑 <b>Адміністраторський доступ активовано!</b>\n\n"
                            "Оплата для цього акаунта пропущена автоматично. Завантажуємо чистий буклет..."
                            if is_uk else
                            "👑 <b>Администраторский доступ активирован!</b>\n\n"
                            "Оплата для вашего акаунта пропущена автоматически. Загружаем чистый буклет..."
                        )
                        if not is_vip:
                            vip_msg = "Ваш оновлений буклет готовий 💛" if is_uk else "Ваш обновлённый буклет готов 💛"
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
                        await self.bot.send_document(chat_id=chat_id, document=FSInputFile(str(recipe_path)))

                        await self.bot.send_message(chat_id=chat_id, text=shopping_text, parse_mode="HTML")

                    await repo.set_status(menu_id, MenuStatus.COMPLETED)
                    logger.info(f"VIP Pipeline successfully finished for Menu ID:{menu_id}")
                    return

                # Стандартный коммерческий режим для остальных пользователей
                configured_price = await get_setting(session, "menu_price_uah", str(self.settings.menu_price))
                price = Decimal(configured_price).quantize(Decimal("0.01"))
                if price <= 0:
                    raise ValueError("Menu price must be positive")
                pay_keyboard = None
                if self.settings.menu_price_stars > 0:
                    try:
                        stars = self.settings.menu_price_stars
                        await repo.set_waiting_for_payment(menu.id, price, stars)
                        invoice = await create_invoice(self.bot, OrderRef(
                            "menu", menu.id, customer_telegram_id, stars))
                        pay_keyboard = get_payment_keyboard(menu.id, invoice, language)
                    except Exception as exc:
                        logger.error("Stars checkout unavailable for menu %s: %s", menu.id, exc)
                if pay_keyboard is None and self.settings.menu_price_stars <= 0:
                    await repo.set_status(menu.id, MenuStatus.IMAGES_READY)

                if preview_image_path and Path(preview_image_path).exists() and chat_id:
                    caption = (
                        f"✨ <b>Ваш превью-гастрономічний сет #{menu.id} готовий!</b>\n\n"
                        f"🔒 <i>На превью нанесені захисні водяні знаки.</i>\n"
                        f"⭐ <b>Повний комплект:</b> {self.settings.menu_price_stars} Stars\n\n"
                        f"Після підтвердження оплати ви отримаєте чистий буклет та рецепти."
                        if is_uk else
                        f"✨ <b>Ваш превью-гастрономический сет #{menu.id} готов!</b>\n\n"
                        f"🔒 <i>На превью нанесены защитные водяные знаки.</i>\n"
                        f"⭐ <b>Полный комплект:</b> {self.settings.menu_price_stars} Stars\n\n"
                        f"После подтверждения оплаты вы получите чистый буклет и рецепты."
                    )
                    if pay_keyboard is None:
                        caption += ("\n\nРахунок можна повторно відкрити у Майстерні."
                                    if is_uk and self.settings.menu_price_stars > 0 else
                                    "\n\nСчёт можно повторно открыть в Мастерской."
                                    if self.settings.menu_price_stars > 0 else
                                    "\n\nОплата тимчасово недоступна." if is_uk else
                                    "\n\nОплата временно недоступна.")

                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=FSInputFile(str(preview_image_path)),
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=pay_keyboard
                    )

                logger.info(f"Pipeline successfully finished for Menu ID:{menu_id}")

            except Exception as proc_exc:
                logger.error(f"Pipeline processing failed for Menu ID:{menu_id}: {proc_exc}", exc_info=True)
                await repo.set_status(menu_id, MenuStatus.FAILED, error_message=str(proc_exc))
                try:
                    await self.bot.send_message(
                        menu.customer.telegram_user_id,
                        "Не удалось подготовить полный комплект. Оплата не выставлена; повторите создание позже.",
                    )
                except Exception:
                    logger.exception("Could not notify customer about failed menu %s", menu_id)

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
