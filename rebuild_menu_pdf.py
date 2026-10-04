"""Repair an existing menu with real dish photos. Run from the project root.

Preview the planned work: python rebuild_menu_pdf.py 45
Actually regenerate (paid API calls): python rebuild_menu_pdf.py 45 --run
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from app.config import get_settings
from app.database.models import FileKind, GenerationStatus, MenuStatus
from app.database.repositories import MenuRepository
from app.database.session import async_session_maker, engine
from app.workers.menu_pipeline import MenuPipeline


async def rebuild(menu_id: int, run: bool) -> None:
    settings = get_settings()
    async with async_session_maker() as session:
        repo = MenuRepository(session)
        menu = await repo.get(menu_id, full=True)
        if menu is None:
            raise SystemExit(f"Заказ #{menu_id} не найден")
        dishes = [item for item in menu.items if item.title != "—"]
        if not dishes:
            raise SystemExit("В заказе нет блюд")
        print(f"Заказ #{menu_id}: {len(dishes)} позиций; старый статус: {menu.status.value}")
        print("Будут заново созданы фотографии каждого блюда и весь PDF за счёт вызовов OpenAI API.")
        if not run:
            print("Это предварительный просмотр. Для запуска добавьте --run")
            return
        if settings.use_mock_images:
            raise SystemExit("Остановлено: установите USE_MOCK_IMAGES=false в .env")
        if settings.openai_api_key.get_secret_value() in ("", "replace_me"):
            raise SystemExit("Остановлено: OPENAI_API_KEY не настроен")

        backup = settings.generated_dir / str(menu_id) / ("backup_before_rebuild_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        for file in menu.files:
            source = Path(file.path)
            if file.kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET) and source.is_file():
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup / source.name)
        for item in dishes:
            item.image_path = None
            item.generation_status = GenerationStatus.PENDING
        menu.status = MenuStatus.QUEUED
        menu.error_message = None
        await session.commit()

    bot = Bot(settings.bot_token)
    pipeline = MenuPipeline(bot, settings, async_session_maker)
    try:
        await pipeline._process(menu_id)
        async with async_session_maker() as session:
            result = await MenuRepository(session).get(menu_id, full=True)
            if result.status == MenuStatus.FAILED:
                raise SystemExit(f"Сборка не завершилась: {result.error_message}")
            print(f"Готово: {result.status.value}. Файлы доступны в Mini App, прежний PDF сохранён: {backup}")
    finally:
        await pipeline.image_service.close()
        await pipeline.recipe_service.client.close()
        await bot.session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Пересобрать PDF существующего заказа")
    parser.add_argument("menu_id", type=int)
    parser.add_argument("--run", action="store_true", help="Разрешить реальные платные запросы к API")
    args = parser.parse_args()
    async def main() -> None:
        try:
            await rebuild(args.menu_id, args.run)
        finally:
            await engine.dispose()
    asyncio.run(main())
