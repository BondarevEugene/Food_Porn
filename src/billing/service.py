# src/billing/service.py
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.exceptions import AccountNotFoundError, InsufficientFundsError
from src.billing.models import Account, Transaction, TransactionType

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_account(self, owner_id: str) -> Account:
        """Получает аккаунт или создает новый (полезно при первом запуске бота пользователем)."""
        result = await self.session.execute(select(Account).where(Account.owner_id == owner_id))
        account = result.scalar_one_or_none()

        if not account:
            account = Account(owner_id=owner_id, available_balance=0, held_balance=0)
            self.session.add(account)
            await self.session.commit()
            await self.session.refresh(account)
        return account

    async def reserve_funds(self, owner_id: str, amount: int, reference_id: str) -> Transaction:
        """
        ШАГ 1: Блокировка средств ПЕРЕД вызовом платного API (например, OpenAI).
        Использует пессимистичную блокировку строки.
        """
        # Блокируем строку Account для чтения и записи другими транзакциями
        stmt = select(Account).where(Account.owner_id == owner_id).with_for_update()
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            raise AccountNotFoundError(f"Аккаунт {owner_id} не найден.")

        if account.available_balance < amount:
            raise InsufficientFundsError(
                f"Недостаточно средств. Доступно: {account.available_balance}, требуется: {amount}"
            )

        # Перемещаем деньги из доступных в замороженные
        account.available_balance -= amount
        account.held_balance += amount

        # Создаем лог-запись типа HOLD
        tx = Transaction(
            account_id=account.id,
            amount=amount,
            type=TransactionType.HOLD,
            reference_id=reference_id,
            description="Блокировка средств под запрос API"
        )
        self.session.add(tx)

        await self.session.commit()
        return tx

    async def commit_hold(self, owner_id: str, amount: int, reference_id: str) -> Transaction:
        """
        ШАГ 2 (Успех): Списание средств ПОСЛЕ успешного ответа API.
        """
        stmt = select(Account).where(Account.owner_id == owner_id).with_for_update()
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()

        # Снимаем деньги из замороженных (окончательно сжигаем)
        account.held_balance -= amount

        tx = Transaction(
            account_id=account.id,
            amount=amount,
            type=TransactionType.COMMIT,
            reference_id=reference_id,
            description="Успешное списание за выполненный запрос"
        )
        self.session.add(tx)

        await self.session.commit()
        return tx

    async def rollback_hold(self, owner_id: str, amount: int, reference_id: str) -> Transaction:
        """
        ШАГ 2 (Провал): Возврат средств на баланс, если API ответил ошибкой (HTTP 500 / Timeout).
        """
        stmt = select(Account).where(Account.owner_id == owner_id).with_for_update()
        result = await self.session.execute(stmt)
        account = result.scalar_one_or_none()

        # Возвращаем деньги из замороженных обратно в доступные
        account.held_balance -= amount
        account.available_balance += amount

        tx = Transaction(
            account_id=account.id,
            amount=amount,
            type=TransactionType.REFUND,
            reference_id=reference_id,
            description="Возврат средств (ошибка на стороне провайдера)"
        )
        self.session.add(tx)

        await self.session.commit()
        return tx