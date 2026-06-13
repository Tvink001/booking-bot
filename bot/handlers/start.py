"""`/start` + main-menu reply-keyboard handlers.

Entry point into the booking flow: tapping the "📅 Book" reply
button sets the FSM to Booking.choosing_service and shows the inline
service picker (which `booking_router` then drives).
"""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.inline import build_service_keyboard
from bot.keyboards.reply import main_menu
from bot.services.sheets import SheetsService
from bot.states import Booking

start_router = Router()

WELCOME = "Hi! I'm a booking bot. What would you like to do?"
HELP_TEXT = (
    "📅 «Book» — make a new appointment\n"
    "📋 «My bookings» — view your appointments\n\n"
    "Use /cancel to abort the current action."
)
NO_SERVICES_YET = "No services yet. Please try later."


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@start_router.message(F.text == "📅 Book")
async def on_book(message: Message, state: FSMContext, sheets: SheetsService) -> None:
    await state.clear()  # defense against tapping mid-flow
    services = await sheets.load_services()
    if not services:
        await message.answer(NO_SERVICES_YET)
        return
    await state.set_state(Booking.choosing_service)
    await message.answer("Choose a service:", reply_markup=build_service_keyboard(services))


@start_router.message(F.text == "❓ Help")
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
