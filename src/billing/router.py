
"""API routes for billing operations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from src.billing.exceptions import InsufficientFundsError
from src.billing.schemas import AccountResponse
from src.billing.service import BillingService

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/accounts/{owner_id}", response_model=AccountResponse)
async def get_account_info(
    owner_id: str,
    db: DbSession,
) -> AccountResponse:
    """Return account information for the specified owner."""
    service = BillingService(db)
    return await service.get_account(owner_id)


@router.post("/execute-paid-action")
async def execute_paid_action(
    owner_id: str,
    db: DbSession,
) -> dict[str, str]:
    """
    Demonstrate the reserve -> execute -> charge/refund workflow.

    The external API call is currently simulated; no real content is generated.
    """
    service = BillingService(db)
    cost = 100
    request_id = str(uuid.uuid4())

    # 1. Reserve funds.
    try:
        await service.reserve_funds(
            owner_id,
            amount=cost,
            reference_id=request_id,
        )
    except InsufficientFundsError as err:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(err),
        ) from err

    # 2. Simulate an external API call.
    # Replace this block with the actual OpenAI/Replicate call.
    api_success = True

    # 3. Finalize the transaction.
    if api_success:
        await service.commit_hold(owner_id, cost, request_id)
        return {
            "status": "success",
            "message": "Content generation simulated; funds charged.",
        }

    await service.rollback_hold(owner_id, cost, request_id)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="External service unavailable. Funds have been refunded.",
    )
