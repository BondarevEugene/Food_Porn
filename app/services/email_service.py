"""Optional printshop email that never reports simulated dispatch as success."""
import asyncio
import mimetypes
import re
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from app.config import get_settings


def normalize_recipient(value: str) -> str:
    address = value.strip()
    if (len(address) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", address)
            or ".." in address):
        raise ValueError("Введите корректный email адрес")
    return address


async def send_ready_order_email(recipient: str, subject: str, paths: list[Path]) -> None:
    settings = get_settings()
    if not all((settings.smtp_host, settings.smtp_user, settings.smtp_password.get_secret_value())):
        raise RuntimeError("Отправка email пока не настроена: укажите SMTP_HOST, SMTP_USER и SMTP_PASSWORD")
    address = normalize_recipient(recipient)
    if not paths or any(not path.is_file() for path in paths):
        raise ValueError("Файлы заказа пока не готовы")
    if sum(path.stat().st_size for path in paths) > 18 * 1024 * 1024:
        raise ValueError("Файлы слишком велики для email; скачайте их из заказа")
    message = EmailMessage()
    message["From"] = settings.smtp_user
    message["To"] = address
    message["Subject"] = subject
    message.set_content("Ваш подарок готов. Печатные файлы и рецепты находятся во вложении. 💛")
    for path in paths:
        mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        kind, subtype = mimetype.split("/", 1)
        payload = await asyncio.to_thread(path.read_bytes)
        message.add_attachment(payload, maintype=kind, subtype=subtype, filename=path.name)
    await aiosmtplib.send(
        message, hostname=settings.smtp_host, port=settings.smtp_port,
        username=settings.smtp_user, password=settings.smtp_password.get_secret_value(),
        use_tls=settings.smtp_use_tls,
    )


async def send_printshop_order_email(email_body: str) -> bool:
    settings = get_settings()
    if not all((settings.smtp_host, settings.smtp_user,
                settings.smtp_password.get_secret_value(), settings.printshop_email)):
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_user
    message["To"] = settings.printshop_email
    message["Subject"] = "New Food Porn print order"
    message.set_content(email_body)
    try:
        await aiosmtplib.send(
            message, hostname=settings.smtp_host, port=settings.smtp_port,
            username=settings.smtp_user, password=settings.smtp_password.get_secret_value(),
            use_tls=settings.smtp_use_tls,
        )
    except Exception:
        return False
    return True
