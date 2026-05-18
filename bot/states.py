"""FSM states for the booking flow. See project_specs.md §8 and §11.

Six linear states. `entering_contact` is a single state that internally
handles two sub-steps (name, then phone) via FSMContext data inspection —
see §11 for the convention.
"""

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    choosing_service = State()
    choosing_master = State()
    choosing_date = State()
    choosing_slot = State()
    entering_contact = State()
    confirming = State()
