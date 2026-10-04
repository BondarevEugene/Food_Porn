# src/bot/payments/service.py
from aiogram.types import LabeledPrice


class TelegramPortmoneBilling:
    @staticmethod
    def create_food_porn_invoice(title: str, description: str, amount_kopecks: int, payload: str):
        """
        Создает параметры для отправки счета (sendInvoice) в Telegram Mini App / Боте.
        :param amount_kopecks: Сумма в минимальных единицах (например, 10000 = 100.00 UAH)
        :param payload: Уникальный идентификатор заказа или подписки (передается обратно в вебхуке)
        """
        prices = [LabeledPrice(label=title, amount=amount_kopecks)]

        return {
            "title": title,
            "description": description,
            "payload": payload,
            # Провайдер-токен от BotFather (выдается при подключении Portmone к боту)
            "provider_token": "PORTMONE_PROVIDER_TOKEN_FROM_BOTFATHER",
            "currency": "UAH",
            "prices": prices,
            "start_parameter": "food-porn-pay",
            # Обязательные флаги для отправки чеков
            "need_name": False,
            "need_phone_number": False,
            "need_email": False,
            "is_flexible": False
        }