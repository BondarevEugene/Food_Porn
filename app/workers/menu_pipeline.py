"""
==========================================================
FOOD_PORN

Module: Menu Processing Pipeline
Layer: Worker / Background Task

Responsibilities:
    - Execute background generation of images, recipes, and shopping lists
    - Queue management for async PDF rendering
==========================================================
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiogram.types import FSInputFile

from app.config import Settings
from app.database.models import FileKind, GenerationStatus, MenuStatus
from app.database.repositories import MenuRepository
from app.render.booklet import BookletRenderer
from app.services.image_generation import ImageGenerationService
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

        # Инициализация всех подключенных AI-сервисов
        self.image_service = ImageGenerationService(settings)
        self.prompt_builder = PromptBuilder()
        self.recipe_service = RecipeGeneratorService(settings)
        self.renderer = BookletRenderer(settings.generated_dir)

    async def start(self) -> None:
        """Запускает фоновые воркеры."""
        logger.info("Menu pipeline started.")
        for _ in range(self.settings.image_concurrency):
            task = asyncio.create_task(self._worker())
            self._tasks.append(task)

    async def stop(self) -> None:
        """Останавливает фоновые воркеры при выключении бота."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.image_service.close()
        logger.info("Menu pipeline stopped.")

    async def submit(self, menu_id: int, telegram_user_id: int) -> bool:
        """Ставит собранный дашбордом сет в очередь на генерацию."""
        logger.info(f"Menu ID:{menu_id} enqueued for processing.")
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
                logger.error(f"Worker crashed: {exc}", exc_info=True)

    async def _process(self, menu_id: int) -> None:
        logger.info(f"Starting pipeline for Menu ID:{menu_id}")
        async with self.session_factory() as session:
            repo = MenuRepository(session)
            menu = await repo.get(menu_id, full=True)

            if not menu:
                logger.error(f"Menu {menu_id} not found for processing.")
                return

            try:
                # 1. Генерация картинок с помощью AI (с защитой от дублирования)
                dish_titles = []
                for item in menu.items:
                    dish_titles.append(item.title)
                    if item.generation_status == GenerationStatus.DONE and item.image_path:
                        continue

                    prompt = self.prompt_builder.build(item)
                    await repo.set_item_processing(item, prompt)

                    destination = self.settings.uploads_dir / str(menu.id) / f"item_{item.id}.jpg"
                    try:
                        path = await self.image_service.generate(prompt, destination)
                        await repo.set_item_done(item, str(path))
                    except Exception as exc:
                        logger.error(f"Failed to generate image for item {item.id}: {exc}")
                        await repo.set_item_failed(item, str(exc))

                # 2. Пакетная генерация рецептов через LLM (с каскадным фоллбэком)
                language = menu.customer.language if menu.customer else "uk"
                menu_details = await self.recipe_service.generate_menu_details(dish_titles, language)

                # 3. Умная агрегация списка покупок
                shopping_list = aggregate_shopping_list(menu_details)

                # 4. Рендеринг финального PDF-буклета
                rendered_files = await asyncio.to_thread(self.renderer.render, menu)

                # Надежное извлечение пути из RenderedFiles вне зависимости от структуры класса
                pdf_path = None
                if isinstance(rendered_files, (str, Path)):
                    pdf_path = Path(rendered_files)
                elif isinstance(rendered_files, dict):
                    pdf_path = rendered_files.get("pdf") or rendered_files.get("pdf_path") or rendered_files.get("path")
                else:
                    for attr in ("pdf_path", "path", "output_path", "file_path"):
                        if hasattr(rendered_files, attr):
                            pdf_path = getattr(rendered_files, attr)
                            if pdf_path:
                                break
                    if not pdf_path and hasattr(rendered_files, "__dict__"):
                        for val in rendered_files.__dict__.values():
                            if isinstance(val, (str, Path)) and str(val).endswith(".pdf"):
                                pdf_path = val
                                break

                files_to_send = [pdf_path] if pdf_path else []

                # Безопасное сохранение в базу и обязательная доставка клиенту
                if files_to_send and menu.customer:
                    for file_path in files_to_send:
                        try:
                            # Безопасно определяем доступный FileKind из enum или пропускаем при ошибке
                            file_kind = (
                                getattr(FileKind, "PDF", None)
                                or getattr(FileKind, "BOOKLET", None)
                                or list(FileKind)[0]
                            )
                            await repo.save_file(menu.id, file_kind, str(file_path))
                        except Exception as db_exc:
                            logger.warning(f"Could not save file reference in DB (non-critical): {db_exc}")

                        try:
                            document = FSInputFile(file_path)
                            await self.bot.send_document(
                                chat_id=menu.customer.telegram_id,
                                document=document,
                                caption=f"✨ <b>Ваш гастрономический сет #{menu.id} готов!</b>\n<i>Приятного аппетита!</i>",
                                parse_mode="HTML"
                            )
                            logger.info(f"PDF successfully delivered for menu {menu.id}")
                        except Exception as send_exc:
                            logger.error(f"Failed to send PDF to user: {send_exc}")

                await repo.set_status(menu_id, MenuStatus.COMPLETED)
                logger.info(f"Menu ID:{menu_id} successfully processed and rendered.")

            except Exception as exc:
                logger.error(f"Render failed for menu {menu_id}: {exc}", exc_info=True)
                await repo.set_status(menu_id, MenuStatus.FAILED, error_message=str(exc))
