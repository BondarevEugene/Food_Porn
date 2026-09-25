"""
==========================================================
FOOD_PORN

Module: Registration FSM States
Layer: Bot FSM
==========================================================
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    name = State()
    phone = State()
    language = State()
    country = State()
    city = State()
    waiting_for_name = State()
    waiting_for_phone = State()