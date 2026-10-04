# src/orchestrator/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.orchestrator.schemas import InstanceCreateRequest, InstanceResponse
from src.orchestrator.service import OrchestratorService

# from src.database.dependencies import get_db_session
# from src.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/orchestrator", tags=["Infrastructure Orchestrator"])


@router.post("/instances", response_model=InstanceResponse)
async def create_instance(
        request: InstanceCreateRequest,
        # current_user = Depends(get_current_user), # Идентификация владельца
        db: AsyncSession = Depends(get_db_session)
):
    """Деплой нового сервиса. Автоматически списывает средства с баланса."""
    service = OrchestratorService(db)
    owner_id = "user_123"  # В реальности: current_user.id

    try:
        instance = await service.deploy_instance(
            owner_id=owner_id,
            name=request.name,
            service_type=request.service_type,
            config=request.config
        )
        return instance
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/instances/{instance_id}/stop", response_model=InstanceResponse)
async def stop_instance(
        instance_id: int,
        db: AsyncSession = Depends(get_db_session)
):
    service = OrchestratorService(db)
    try:
        return await service.stop_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))