"""
==========================================================
FOOD_PORN

Module: Legacy Portmone HTTP Compatibility Routes
Layer: HTTP Interface

Responsibilities:
    - Preserve historical endpoint paths used by deployment checks
    - Reject client-controlled payment-link creation
    - Never treat an unauthenticated callback as proof of payment
==========================================================
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/portmone", tags=["Portmone compatibility"])


@router.post("/generate-link", include_in_schema=False)
async def generate_link_disabled() -> None:
    """Payment links are created only by the authenticated Telegram sandbox flow."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use the private VIP/admin Portmone sandbox flow",
    )


@router.post("/callback")
async def portmone_callback_ignored() -> dict[str, str]:
    """A browser/provider redirect is not payment proof; verification is server-side."""
    return {
        "status": "ignored",
        "message": "Use server-side Portmone status verification",
    }
