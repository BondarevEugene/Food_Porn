from aiogram.fsm.state import State, StatesGroup


class MenuStates(StatesGroup):
    waiting_for_dishes = State()
    waiting_for_confirmation = State()
