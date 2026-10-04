"""
==========================================================
FOOD_PORN

Module: Printshop Dispatch Service
Layer: Service

Responsibilities:
    - Dispatch approved production PDFs to printshop via email
==========================================================
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from app.config import Settings

logger = logging.getLogger(__name__)


class PrintshopService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def dispatch_to_printshop(self, menu_id: int, pdf_path: Path, customer_info: str) -> bool:
        """Отправляет готовый чистый PDF в типографию по электронной почте."""
        if not self.settings.printshop_email:
            logger.warning("Printshop email is not configured in settings. Skipping dispatch.")
            return False

        if not pdf_path.exists():
            logger.error(f"Printshop dispatch failed: PDF file not found at {pdf_path}")
            return False

        message = EmailMessage()
        if not self.settings.smtp_host or not self.settings.smtp_user:
            logger.warning("Printshop dispatch skipped: SMTP is not configured")
            return False

        message["From"] = self.settings.smtp_user
        message["To"] = self.settings.printshop_email
        message["Subject"] = f"🖨 New Print Order #{menu_id} — Food_Porn"

        body = (
            f"Здравствуйте! Поступил новый заказ на печать гастрономического буклета.\n\n"
            f"Номер заказа: #{menu_id}\n"
            f"Клиент: {customer_info}\n\n"
            f"Файл для печати прикреплен к этому письму."
        )
        message.set_content(body)

        # Прикрепляем PDF-файл
        try:
            with open(pdf_path, "rb") as f:
                file_data = f.read()
                file_name = pdf_path.name
            message.add_attachment(file_data, maintype="application", subtype="pdf", filename=file_name)
        except Exception as e:
            logger.error(f"Failed to attach PDF for printshop: {e}")
            return False

        # Отправка через SMTP (если настроено) либо логирование
        try:
            await aiosmtplib.send(
                message,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_user,
                password=self.settings.smtp_password.get_secret_value(),
                use_tls=self.settings.smtp_use_tls,
            )
            logger.info("Print order %s sent to %s", menu_id, self.settings.printshop_email)
            return True
        except Exception as smtp_exc:
            logger.error(f"SMTP dispatch failed: {smtp_exc}")
            return False
