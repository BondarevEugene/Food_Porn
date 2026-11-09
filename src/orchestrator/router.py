
"""API routes for infrastructure orchestration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from src.orchestrator.schemas import InstanceCreateRequest, InstanceResponse
from src.orchestrator.service import OrchestratorService

router = APIRouter(
    prefix="/api/v1/orchestrator",
    tags=["Infrastructure Orchestrator"],
)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/instances", response_model=InstanceResponse)
async def create_instance(
    request: InstanceCreateRequest,
    db: DbSession,
) -> InstanceResponse:
    """Deploy a new service and charge the owner's balance."""
    service = OrchestratorService(db)

    # TODO: Replace this placeholder with the authenticated user's ID.
    owner_id = "user_123"

    try:
        return await service.deploy_instance(
            owner_id=owner_id,
            name=request.name,
            service_type=request.service_type,
            config=request.config,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(err),
        ) from err
    except RuntimeError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(err),
        ) from err


@router.post(
    "/instances/{instance_id}/stop",
    response_model=InstanceResponse,
)
async def stop_instance(
    instance_id: int,
    db: DbSession,
) -> InstanceResponse:
    """Stop a deployed service instance."""
    service = OrchestratorService(db)

    try:
        return await service.stop_instance(instance_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
