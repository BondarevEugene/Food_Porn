"""Aiogram adapter for the already fenced Little Legend PDF delivery."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import BufferedInputFile


class AiogramPDFSender:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_pdf(
        self, *, chat_id: int, pdf: bytes, filename: str,
    ) -> int:
        if chat_id <= 0 or not pdf.startswith(b"%PDF-"):
            raise ValueError("Valid Telegram recipient and PDF required")
        if not filename.startswith("little-legend-") or not filename.endswith(".pdf"):
            raise ValueError("Invalid book filename")
        message = await self._bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(pdf, filename=filename),
        )
        return message.message_id
