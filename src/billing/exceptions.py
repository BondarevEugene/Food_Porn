# src/billing/exceptions.py

class BillingError(Exception):
    """Базовый класс для всех ошибок биллинга."""
    pass


class InsufficientFundsError(BillingError):
    """Ошибка: Недостаточно средств на балансе."""
    pass


class QuotaExceededError(BillingError):
    """Ошибка: Превышен лимит запросов (квота)."""
    pass


class AccountNotFoundError(BillingError):
    """Ошибка: Аккаунт не найден."""
    pass
