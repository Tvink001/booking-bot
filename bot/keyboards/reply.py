"""Reply keyboards: main menu and 'Поделиться контактом'.

Reply keyboards stay on-screen until removed via ReplyKeyboardRemove.
Use `remove()` at the end of the booking flow to clear the share-contact
keyboard after the phone step.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записатися")],
            [KeyboardButton(text="📋 Мої записи")],
            [KeyboardButton(text="❓ Допомога")],
        ],
        resize_keyboard=True,
    )


def share_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
