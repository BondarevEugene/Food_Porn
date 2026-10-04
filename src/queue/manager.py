# src/queue/manager.py
import logging
from collections.abc import Callable
from typing import Any

from src.queue.worker import food_porn_queue

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Фасад для управления очередью генерации контента в FoodPorn.
    Позволяет отправлять задачи на выполнение с гарантией соблюдения лимитов API.
    """

    @staticmethod
    async def schedule_generation(task_func: Callable, *args, **kwargs) -> Any:
        """
        Ставит задачу на генерацию в общую очередь.
        Если заняты все слоты (concurrency_limit), задача будет ожидать своей очереди.

        :param task_func: Асинхронная функция генерации (например, запрос к OpenAI/Replicate)
        """
        logger.info(f"Задача {task_func.__name__} добавлена в очередь генерации FoodPorn.")

        # Передаем задачу в глобальный воркер
        result = await food_porn_queue.enqueue(task_func, *args, **kwargs)
        return result

    @classmethod
    def initialize(cls):
        """Инициализация фонового воркера при старте FastAPI приложения."""
        food_porn_queue.init_background_worker()
        logger.info("Фоновый воркер очереди FoodPorn успешно запущен.")