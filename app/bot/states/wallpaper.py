"""
==========================================================
FOOD_PORN

Module: Wallpaper FSM States
Layer: Bot FSM
==========================================================
"""

from aiogram.fsm.state import State, StatesGroup


class WallpaperStates(StatesGroup):
    waiting_for_photos = State()
    waiting_for_goals = State()