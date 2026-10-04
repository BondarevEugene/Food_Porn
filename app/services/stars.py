"""Telegram Stars invoices and receipt validation for complete digital orders."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import LabeledPrice
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import FileKind, Menu, MenuStatus, WallpaperOrder


@dataclass(frozen=True)
class OrderRef:
    kind: str
    order_id: int
    owner_id: int
    stars: int

    @property
    def payload(self) -> str:
        return f"fp:{self.kind}:{self.order_id}:{self.owner_id}:{self.stars}"


def parse_payload(payload: str) -> OrderRef | None:
    try:
        prefix, kind, order_id, owner_id, stars = payload.split(":")
        if prefix != "fp" or kind not in {"menu", "wallpaper"}:
            return None
        result = OrderRef(kind, int(order_id), int(owner_id), int(stars))
        if min(result.order_id, result.owner_id, result.stars) < 1 or result.payload != payload:
            return None
        return result
    except (ValueError, AttributeError):
        return None


async def create_invoice(bot: Bot, ref: OrderRef) -> str:
    if ref.stars < 1:
        raise ValueError("The Star price has not been configured")
    title = "Гастрономічний подарунок" if ref.kind == "menu" else "Історія п’яти бажань"
    return await bot.create_invoice_link(
        title=title,
        description="Повний цифровий набір: готові зображення і файли для друку",
        payload=ref.payload,
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=ref.stars)],
    )


async def payment_is_available(
    factory: async_sessionmaker[AsyncSession], ref: OrderRef,
) -> bool:
    async with factory() as session:
        if ref.kind == "menu":
            menu = await session.get(Menu, ref.order_id)
            if (menu is None or menu.is_paid or menu.stars_amount != ref.stars
                    or menu.status != MenuStatus.WAITING_FOR_PAYMENT):
                return False
            await session.refresh(menu, ["customer", "files"])
            files = {file.kind: file.path for file in menu.files}
            return (menu.customer.telegram_user_id == ref.owner_id
                    and all(kind in files and Path(files[kind]).is_file()
                            for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)))
        order = await session.get(WallpaperOrder, ref.order_id)
        if order is None:
            return False
        return (order.telegram_user_id == ref.owner_id and not order.paid
                and order.stars_amount == ref.stars
                and Path(order.mobile_path).is_file() and Path(order.desktop_path).is_file())


async def record_payment(
    factory: async_sessionmaker[AsyncSession], ref: OrderRef, charge_id: str,
) -> str:
    """Persist before delivery; return new, same or duplicate (needs a refund)."""
    async with factory() as session:
        if ref.kind == "menu":
            query = select(Menu).where(Menu.id == ref.order_id).with_for_update()
            menu = (await session.execute(query)).scalar_one_or_none()
            if menu is None:
                return "duplicate"
            await session.refresh(menu, ["customer", "files"])
            if menu.customer.telegram_user_id != ref.owner_id or menu.stars_amount != ref.stars:
                return "duplicate"
            if menu.is_paid:
                return "same" if menu.payment_id == charge_id else "duplicate"
            files = {file.kind: Path(file.path) for file in menu.files}
            if (menu.status != MenuStatus.WAITING_FOR_PAYMENT or any(
                kind not in files or not files[kind].is_file()
                for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)
            )):
                return "duplicate"
            menu.is_paid = True
            menu.payment_id = charge_id
            menu.payment_system = "telegram_stars"
            menu.status = MenuStatus.PAID
        else:
            query = select(WallpaperOrder).where(WallpaperOrder.id == ref.order_id).with_for_update()
            order = (await session.execute(query)).scalar_one_or_none()
            if order is None or order.telegram_user_id != ref.owner_id or order.stars_amount != ref.stars:
                return "duplicate"
            if order.paid:
                return "same" if order.payment_id == charge_id else "duplicate"
            if not Path(order.mobile_path).is_file() or not Path(order.desktop_path).is_file():
                return "duplicate"
            order.paid = True
            order.payment_id = charge_id
            order.payment_system = "telegram_stars"
        await session.commit()
        return "new"
