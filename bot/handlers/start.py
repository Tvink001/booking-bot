"""`/start` handler — placeholder reply until later prompts add the menu."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer("Бот працює. Команди з'являться у наступних промптах.")
