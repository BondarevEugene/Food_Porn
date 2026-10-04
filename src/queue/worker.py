# src/queue/worker.py
import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

class ImageGenerationQueue:
    def __init__(self, concurrency_limit: int = 1):
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self._queue = asyncio.Queue()
        self._worker_task = None

    async def enqueue(self, func: Callable, *args, **kwargs) -> Any:
        """Постановка задачи в очередь с ожиданием результата."""
        future = asyncio.get_running_loop().create_future()
        await self._queue.put((func, args, kwargs, future))
        return await future

    async def start_worker(self):
        """Фоновый воркер, выбирающий задачи по мере освобождения слотов."""
        while True:
            func, args, kwargs, future = await self._queue.get()
            async with self._semaphore:
                try:
                    # Выполняем задачу (например, запрос к OpenAI API)
                    result = await func(*args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    logger.error(f"Ошибка в очереди генерации: {e}")
                    future.set_exception(e)
                finally:
                    self._queue.task_done()

    def init_background_worker(self):
        if not self._worker_task:
            self._worker_task = asyncio.create_async_task(self.start_worker())

# Глобальный инстанс очереди для FoodPorn (concurrency = 1 строго по требованиям)
food_porn_queue = ImageGenerationQueue(concurrency_limit=1)