"""
==========================================================
FOOD_PORN

Module: WayForPay HTTP Endpoints
Layer: Transport / Payment API

Responsibilities:
    - Serve a short-lived hosted-checkout bridge page
    - Verify signed provider callbacks before granting entitlement
    - Apply approved payments atomically and idempotently
==========================================================
"""

from __future__ import annotations

import html
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.database.models import Menu, WallpaperOrder, WayForPayPayment
from app.database.repositories import WayForPayPaymentRepository
from app.database.session import async_session_maker
from app.services.wayforpay import (
    WAYFORPAY_CHECKOUT_URL,
    WayForPayError,
    WayForPayService,
    apply_verified_payment,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/wayforpay", tags=["WayForPay"])


def _checkout_document(fields: dict[str, str | list[str]]) -> str:
    inputs: list[str] = []
    for name, value in fields.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            inputs.append(
                f'<input type="hidden" name="{html.escape(name, quote=True)}" value="{html.escape(str(item), quote=True)}">'
            )
    return f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>WayForPay · Food Porn</title>
<style>body{{margin:0;background:#11100f;color:#f2dfbf;font-family:system-ui;display:grid;place-items:center;min-height:100vh}}
.card{{max-width:520px;padding:36px;text-align:center;border:1px solid #735f43;border-radius:22px;background:#1b1815}}
button{{border:0;border-radius:14px;padding:15px 24px;background:#d2a65e;color:#17120c;font-weight:800;font-size:16px}}</style>
</head><body><main class="card"><h1>Безпечна оплата</h1><p>Переходимо на захищену сторінку WayForPay…</p>
<form id="checkout" method="post" action="{WAYFORPAY_CHECKOUT_URL}">{''.join(inputs)}
<button type="submit">Перейти до оплати</button></form></main>
<script>window.setTimeout(function(){{document.getElementById('checkout').submit()}},350);</script></body></html>"""


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        form = await request.form()
        return dict(form)
    except (ValueError, RuntimeError):
        return {}


async def _product_is_paid(payment: WayForPayPayment) -> bool:
    async with async_session_maker() as session:
        if payment.product == "menu":
            record = await session.get(Menu, int(payment.reference_id))
            return bool(record and record.is_paid)
        record = await session.get(WallpaperOrder, int(payment.reference_id))
        return bool(record and record.paid)


@router.get("/checkout/{checkout_token}", response_class=HTMLResponse)
async def checkout(checkout_token: str) -> HTMLResponse:
    settings = get_settings()
    service = WayForPayService(settings)
    async with async_session_maker() as session:
        payment = await WayForPayPaymentRepository(session).by_checkout_token(checkout_token)
        if payment is None:
            raise HTTPException(404, "Payment link not found")
        if payment.status == "approved":
            return HTMLResponse("<h2>Оплату вже підтверджено. Поверніться до Telegram.</h2>")
        if payment.status != "pending":
            raise HTTPException(409, "Payment link is no longer active")
        if not payment.test_mode and await _product_is_paid(payment):
            raise HTTPException(409, "Order is already paid")
        try:
            fields = service.form_fields(payment)
        except WayForPayError as exc:
            logger.error("WayForPay checkout configuration error: %s", exc)
            raise HTTPException(503, "Card payment is temporarily unavailable") from exc
    return HTMLResponse(
        _checkout_document(fields),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    payload = await _payload(request)
    order_reference = str(payload.get("orderReference", ""))
    if not order_reference:
        raise HTTPException(400, "Missing orderReference")
    service = WayForPayService(get_settings())
    async with async_session_maker() as session:
        repository = WayForPayPaymentRepository(session)
        payment = await repository.by_order_reference(order_reference, lock=True)
        if payment is None or not service.verify_provider_payload(payment, payload):
            logger.warning("Rejected unsigned or mismatched WayForPay callback: %s", order_reference)
            raise HTTPException(400, "Invalid payment signature")

        try:
            await apply_verified_payment(session, payment, payload)
        except WayForPayError as exc:
            raise HTTPException(409, str(exc)) from exc

    return JSONResponse(service.callback_ack(order_reference))


@router.get("/return", response_class=HTMLResponse)
async def payment_return() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Food Porn · Payment</title><style>body{margin:0;background:#11100f;color:#f2dfbf;font-family:system-ui;display:grid;place-items:center;min-height:100vh}.card{max-width:520px;padding:38px;text-align:center;border:1px solid #735f43;border-radius:22px;background:#1b1815}</style></head>
<body><main class="card"><h1>Дякуємо 💛</h1><p>Поверніться до Telegram і натисніть «Перевірити оплату». Файли відкриються тільки після підтвердження банком.</p></main></body></html>""",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
