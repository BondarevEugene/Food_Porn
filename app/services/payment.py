"""
==========================================================
FOOD_PORN

Module: Payment Service (Portmone & Redsys)
Layer: Service

Responsibilities:
    - Generate secure checkout links for Portmone (UAH) and Redsys (EUR)
==========================================================
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_portmone_invoice(self, menu_id: int, amount: float, description: str) -> str:
        """Генерирует ссылку на оплату через Portmone."""
        payee_id = self.settings.portmone_payee_id
        checkout_url = (
            f"https://www.portmone.com.ua/gateway/?"
            f"shop_order_number={menu_id}&"
            f"payee_id={payee_id}&"
            f"bill_amount={amount}&"
            f"description={description}"
        )
        logger.info(f"Generated Portmone invoice for menu {menu_id}: {amount} {self.settings.currency}")
        return checkout_url

    def create_redsys_invoice(self, menu_id: int, amount: float, description: str) -> str:
        """Генерирует ссылку на оплату через Redsys (международные карты)."""
        merchant_code = self.settings.redsys_merchant_code
        currency = self.settings.redsys_currency
        checkout_url = (
            f"https://sis.redsys.es/sis/realizarPago?"
            f"merchantCode={merchant_code}&"
            f"amount={int(amount * 100)}&"
            f"currency={currency}&"
            f"order={menu_id:04d}&"
            f"merchantName=Food_Porn"
        )
        logger.info(f"Generated Redsys invoice for menu {menu_id}: {amount} EUR")
        return checkout_url
