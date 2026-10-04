# src/payment/portmone/router.py
import os
import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db_session
from app.database.models import Menu, MenuStatus
from src.billing.models import Account, Transaction, TransactionType

from src.payment.portmone.schemas import (
    PortmonePaymentLinkRequest,
    PortmonePaymentLinkResponse,
)
from src.payment.portmone.service import PortmoneService
from app.services.pdf_generator import generate_order_pdf
from app.services.pricing_service import get_current_price

from aiogram import Bot
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portmone", tags=["Payment Gateway (Professional)"])


@router.post("/generate-link", response_model=PortmonePaymentLinkResponse,
             summary="Генерация платежной ссылки Portmone с учетом динамических цен")
async def generate_link(
        request_data: PortmonePaymentLinkRequest,
        db: AsyncSession = Depends(get_db_session)
):
    """
    Эндпоинт для бота. Генерирует защищенную ссылку на платежный шлюз Portmone,
    учитывая актуальную стоимость продукта на текущую дату.
    """
    try:
        service = PortmoneService(db)

        # Получаем актуальную цену из базы с учетом расписания дат
        current_active_price = await get_current_price(db, product_key="collage_uah")
        amount_to_charge = int(current_active_price * 100) if request_data.amount <= 0 else request_data.amount

        url, order_id = await service.create_payment_url(
            owner_id=request_data.owner_id,
            amount_cents=amount_to_charge
        )
        logger.info(
            f"Сгенерирована платежная ссылка для owner_id={request_data.owner_id}, order_id={order_id}, сумма={amount_to_charge}")
        return PortmonePaymentLinkResponse(payment_url=url, order_id=order_id)
    except Exception as e:
        logger.exception("Ошибка при генерации платежной ссылки Portmone")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сформировать ссылку на оплату"
        )


@router.post("/callback", summary="Вебхук обработки результатов оплаты от Portmone")
async def portmone_callback(
        request: Request,
        db: AsyncSession = Depends(get_db_session)
):
    """
    Result URL (вебхук). Обрабатывает уведомления от Portmone с соблюдением стандартов промышленного биллинга:
    - Идемпотентность (защита от повторных начислений).
    - Атомарность транзакций базы данных.
    - Автоматическая генерация PDF-чека и отправка клиенту в Telegram.
    """
    try:
        payload = await request.form()
        payload_dict = dict(payload)
        logger.info(f"Получен webhook от Portmone: {payload_dict}")

        order_id_str = payload.get("SHOPORDERNUMBER")
        payment_status = payload.get("RESULT")
        amount_str = payload.get("BILL_AMOUNT")
        shop_bill_id = payload.get("SHOPBILLID")

        if not order_id_str or not order_id_str.isdigit():
            logger.warning(f"Некорректный номер заказа в webhook: {order_id_str}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Order ID")

        menu_id = int(order_id_str)

        menu = await db.get(Menu, menu_id)
        if not menu:
            logger.error(f"Заказ #{menu_id} не найден в базе данных")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")

        current_status = getattr(menu, "status", None)
        if current_status == MenuStatus.PAID or current_status == "PAID":
            logger.info(f"Заказ #{menu_id} уже имеет статус PAID. Повторный webhook проигнорирован.")
            return {"status": "ok", "message": "Already processed"}

        if shop_bill_id:
            existing_tx = await db.scalar(
                select(Transaction).where(Transaction.reference_id == f"portmone_{shop_bill_id}")
            )
            if existing_tx:
                logger.info(f"Транзакция portmone_{shop_bill_id} уже зарегистрирована. Пропуск.")
                return {"status": "ok", "message": "Transaction already recorded"}

        if payment_status == "0":
            if hasattr(MenuStatus, "PAID"):
                menu.status = MenuStatus.PAID
            else:
                menu.status = "PAID"

            owner_id = getattr(menu, "customer_id", None) or getattr(menu, "telegram_user_id", None)
            if not owner_id:
                logger.error(f"У заказа #{menu_id} отсутствует идентификатор владельца")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Customer ID missing")

            account = await db.scalar(select(Account).where(Account.owner_id == str(owner_id)))
            if not account:
                account = Account(owner_id=str(owner_id), available_balance=0, held_balance=0)
                db.add(account)
                await db.flush()

            try:
                amount_val = float(amount_str) if amount_str else 0.0
            except (ValueError, TypeError):
                amount_val = 0.0

            amount_cents = int(amount_val * 100)
            account.available_balance += amount_cents

            transaction = Transaction(
                account_id=account.id,
                amount=amount_cents,
                type=TransactionType.DEPOSIT,
                reference_id=f"portmone_{shop_bill_id}" if shop_bill_id else f"portmone_order_{menu_id}",
                description=f"Оплата заказа/сета #{menu.id} через Portmone шлюз"
            )
            db.add(transaction)
            await db.commit()
            logger.info(f"Успешно зачислено {amount_cents} центов на счет владельца {owner_id} по заказу #{menu_id}")

            # Генерация PDF-чека и отправка клиенту в Telegram
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            customer_name = getattr(menu, "name", f"User_{owner_id}")

            try:
                pdf_path = generate_order_pdf(
                    order_id=menu.id,
                    customer_name=customer_name,
                    amount_uah=amount_val
                )
            except Exception as pdf_err:
                logger.error(f"Не удалось сгенерировать PDF-чек для заказа #{menu.id}: {pdf_err}")
                pdf_path = None

            if bot_token:
                try:
                    bot = Bot(token=bot_token)
                    if pdf_path and os.path.exists(pdf_path):
                        await bot.send_document(
                            chat_id=int(owner_id),
                            document=FSInputFile(pdf_path),
                            caption=(
                                f"✅ **Оплата успешно получена!**\n\n"
                                f"• Заказ: `#{menu.id}`\n"
                                f"• Сумма: `{amount_val:.2f} UAH`\n"
                                f"• Статус: Передан в работу 🍷\n\n"
                                f"Электронный чек и спецификация во вложении."
                            ),
                            parse_mode="Markdown"
                        )
                    else:
                        await bot.send_message(
                            chat_id=int(owner_id),
                            text=(
                                f"✅ **Оплата успешно получена!**\n\n"
                                f"• Заказ: `#{menu.id}`\n"
                                f"• Сумма: `{amount_val:.2f} UAH`\n"
                                f"• Статус: Передан в работу 🍷"
                            ),
                            parse_mode="Markdown"
                        )
                    await bot.session.close()
                except Exception as tg_err:
                    logger.error(f"Не удалось отправить уведомление в Telegram пользователю {owner_id}: {tg_err}")

        else:
            logger.warning(f"Платеж по заказу #{menu_id} отклонен шлюзом. Код результата: {payment_status}")
            if hasattr(MenuStatus, "CANCELED"):
                menu.status = MenuStatus.CANCELED
            else:
                menu.status = "CANCELED"
            await db.commit()

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Критическая ошибка при обработке Portmone callback")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Billing Error"
        )
