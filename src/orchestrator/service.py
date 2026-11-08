"""Service layer for deploying and stopping infrastructure instances."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.exceptions import InsufficientFundsError
from src.billing.service import BillingService
from src.orchestrator.docker_api import DockerManager
from src.orchestrator.models import (
    InstanceStatus,
    ServiceInstance,
    ServiceType,
)

# One-time instance creation charge in the platform's smallest currency units.
INSTANCE_CREATION_PRICE = 5000


class OrchestratorService:
    """Coordinate billing, database records, and Docker operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.docker = DockerManager()
        self.billing = BillingService(session)

    async def deploy_instance(
        self,
        owner_id: str,
        name: str,
        service_type: ServiceType,
        config: dict,
    ) -> ServiceInstance:
        """Charge for and deploy a service instance."""
        try:
            await self.billing.reserve_funds(
                owner_id,
                INSTANCE_CREATION_PRICE,
                f"deploy_{name}",
            )
            await self.billing.commit_hold(
                owner_id,
                INSTANCE_CREATION_PRICE,
                f"deploy_{name}",
            )
        except InsufficientFundsError as err:
            raise ValueError(f"Insufficient funds to deploy service: {err}") from err

        instance = ServiceInstance(
            owner_id=owner_id,
            name=name,
            service_type=service_type,
            config=config,
            status=InstanceStatus.STARTING,
        )
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)

        image_name = (
            "omnifactory/tg-runner:latest"
            if service_type == ServiceType.TELEGRAM_BOT
            else "omnifactory/fastapi-base:latest"
        )

        try:
            container_id = await self.docker.spawn_container(
                image_name=image_name,
                env_vars=config,
            )

            instance.container_id = container_id
            instance.status = InstanceStatus.RUNNING
            await self.session.commit()

        except Exception as err:
            instance.status = InstanceStatus.FAILED
            await self.session.commit()
            # TODO: Add automatic refund handling if deployment fails.
            raise RuntimeError(f"Container startup failed: {err}") from err

        return instance

    async def stop_instance(self, instance_id: int) -> ServiceInstance:
        """Stop a deployed service instance."""
        instance = await self.session.get(ServiceInstance, instance_id)
        if instance is None or not instance.container_id:
            raise ValueError("Instance not found or not running")

        await self.docker.stop_container(instance.container_id)
        instance.status = InstanceStatus.STOPPED
        await self.session.commit()

        return instance
