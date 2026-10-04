# src/orchestrator/service.py
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.exceptions import InsufficientFundsError
from src.billing.service import BillingService
from src.orchestrator.docker_api import DockerManager
from src.orchestrator.models import InstanceStatus, ServiceInstance, ServiceType

# Базовая стоимость создания инстанса (может быть ежемесячной подпиской)
INSTANCE_CREATION_PRICE = 5000  # 50.00 у.е. (в минимальных единицах)


class OrchestratorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.docker = DockerManager()
        self.billing = BillingService(session)

    async def deploy_instance(self, owner_id: str, name: str, service_type: ServiceType,
                              config: dict) -> ServiceInstance:
        """
        Полный цикл деплоя: списание средств -> запись в реестр -> запуск контейнера.
        """
        # 1. Проверяем баланс и списываем деньги за деплой
        try:
            # Сразу коммитим списание (в отличие от hold), так как это разовая услуга
            await self.billing.reserve_funds(owner_id, INSTANCE_CREATION_PRICE, f"deploy_{name}")
            await self.billing.commit_hold(owner_id, INSTANCE_CREATION_PRICE, f"deploy_{name}")
        except InsufficientFundsError as e:
            raise ValueError(f"Недостаточно средств для деплоя сервиса: {str(e)}")

        # 2. Создаем запись в БД со статусом STARTING
        instance = ServiceInstance(
            owner_id=owner_id,
            name=name,
            service_type=service_type,
            config=config,
            status=InstanceStatus.STARTING
        )
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)

        # 3. Физический запуск в Docker
        image_name = "omnifactory/tg-runner:latest" if service_type == ServiceType.TELEGRAM_BOT else "omnifactory/fastapi-base:latest"

        try:
            container_id = await self.docker.spawn_container(
                image_name=image_name,
                env_vars=config
            )

            # 4. Успех: обновляем статус
            instance.container_id = container_id
            instance.status = InstanceStatus.RUNNING
            await self.session.commit()

        except Exception as e:
            # Провал: маркируем как FAILED
            instance.status = InstanceStatus.FAILED
            await self.session.commit()
            # Здесь можно добавить логику автоматического возврата средств (refund)
            raise RuntimeError(f"Ошибка запуска контейнера: {str(e)}")

        return instance

    async def stop_instance(self, instance_id: int) -> ServiceInstance:
        """Принудительная остановка (ручная или скриптом-кроном при неоплате)."""
        instance = await self.session.get(ServiceInstance, instance_id)
        if not instance or not instance.container_id:
            raise ValueError("Инстанс не найден или не запущен")

        await self.docker.stop_container(instance.container_id)
        instance.status = InstanceStatus.STOPPED
        await self.session.commit()

        return instance