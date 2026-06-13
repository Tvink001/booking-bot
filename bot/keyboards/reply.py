"""Reply keyboards: main menu and 'Share contact'.

Reply keyboards stay on-screen until removed via ReplyKeyboardRemove.
Use `remove()` at the end of the booking flow to clear the share-contact
keyboard after the phone step.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Book")],
            [KeyboardButton(text="📋 My bookings")],
            [KeyboardButton(text="❓ Help")],
        ],
        resize_keyboard=True,
    )


def share_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share contact", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
