"""
==========================================================
FOOD_PORN

Module: FSM States
Layer: Presentation
==========================================================
"""
from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    language = State()
    name = State()
    phone = State()
    country = State()  # <-- добавлено
    city = State()     # <-- добавлено

class MenuStates(StatesGroup):
    """Заглушка для обратной совместимости"""
    item = State()
    cover_photo = State()
    spread_photo = State()
    review = State()

class PremiumMenuStates(StatesGroup):
    waiting_for_dish_name = State()
    waiting_for_cover = State()
    waiting_for_spread = State()