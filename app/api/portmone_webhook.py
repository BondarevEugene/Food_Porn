"""Public webhook endpoint retained for compatibility.

An unauthenticated POST body is never proof of payment. The Telegram bot
queries the provider server-side using merchant credentials before delivery.
This endpoint deliberately cannot unlock either product.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/portmone", tags=["Portmone"])


@router.post("/webhook")
async def portmone_webhook() -> dict[str, str]:
    return {"status": "ignored", "message": "Use the Telegram payment verification button"}
