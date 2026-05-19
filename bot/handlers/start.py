"""`/start` + main-menu reply-keyboard handlers.

Entry point into the booking flow: tapping the "📅 Записатися" reply
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

WELCOME = "Привет! Я бот для записи. Что хочешь сделать?"
HELP_TEXT = (
    "📅 «Записатися» — создать новую запись\n"
    "📋 «Мои записи» — посмотреть свои записи\n\n"
    "Для отмены текущего действия используй /cancel."
)
NO_SERVICES_YET = "Услуг пока нет. Попробуйте позже."


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@start_router.message(F.text == "📅 Записатися")
async def on_book(message: Message, state: FSMContext, sheets: SheetsService) -> None:
    await state.clear()  # defense against tapping mid-flow
    services = await sheets.load_services()
    if not services:
        await message.answer(NO_SERVICES_YET)
        return
    await state.set_state(Booking.choosing_service)
    await message.answer("Выберите услугу:", reply_markup=build_service_keyboard(services))


@start_router.message(F.text == "❓ Допомога")
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
