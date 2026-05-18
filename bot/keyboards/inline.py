"""Inline keyboard builders.

Pure functions: input data → InlineKeyboardMarkup. No I/O. The booking
handler loads data via SheetsService/CalendarService and passes it here.

Unavailable date cells use a combining-strikethrough label (U+0336) plus
a `NavCB("noop_date")` callback — Telegram doesn't truly disable inline
buttons, so we render them visually disabled and intercept the tap to
emit a toast.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import (
    BookingActionCB,
    DateCB,
    MasterCB,
    NavCB,
    ServiceCB,
    SlotCB,
)
from bot.models import Blackout, Master, Service

_STRIKE = "̶"  # combining long stroke overlay


def _strike(text: str) -> str:
    return "".join(c + _STRIKE for c in text)


def _chunked(items: list[datetime], size: int) -> Iterable[list[datetime]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _nav_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="← Назад", callback_data=NavCB(action="back").pack()),
        InlineKeyboardButton(text="✖ Скасувати", callback_data=NavCB(action="cancel").pack()),
    ]


def build_service_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        if not s.is_active:
            continue
        label = f"{s.name} · {s.duration_min} хв · {s.price} грн"
        kb.button(text=label, callback_data=ServiceCB(service_id=s.id))
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text="✖ Скасувати", callback_data=NavCB(action="cancel").pack()))
    return kb.as_markup()


def build_master_keyboard(masters: list[Master], service: Service) -> InlineKeyboardMarkup:
    eligible_ids = set(service.master_ids) if service.master_ids else None
    kb = InlineKeyboardBuilder()
    for m in masters:
        if not m.is_active:
            continue
        if eligible_ids is not None and m.id not in eligible_ids:
            continue
        kb.button(text=m.name, callback_data=MasterCB(master_id=m.id))
    kb.adjust(1)
    kb.row(*_nav_row())
    return kb.as_markup()


def build_date_keyboard(
    start_date: date, master: Master, blackouts: list[Blackout]
) -> InlineKeyboardMarkup:
    """14-day grid (2 rows × 7 cols).

    Cells outside `master.work_days` or in `blackouts` (matching master_id
    or '*') get a strike-through label + noop callback.
    """
    blackout_dates = {b.date for b in blackouts if b.master_id in ("*", master.id)}
    buttons: list[InlineKeyboardButton] = []
    for i in range(14):
        d = start_date + timedelta(days=i)
        unavailable = d.isoweekday() not in master.work_days or d in blackout_dates
        label_base = d.strftime("%d.%m")
        if unavailable:
            buttons.append(
                InlineKeyboardButton(
                    text=_strike(label_base),
                    callback_data=NavCB(action="noop_date").pack(),
                )
            )
        else:
            buttons.append(
                InlineKeyboardButton(
                    text=label_base,
                    callback_data=DateCB(iso_date=d.isoformat()).pack(),
                )
            )

    kb = InlineKeyboardBuilder()
    kb.row(*buttons[:7])
    kb.row(*buttons[7:])
    kb.row(*_nav_row())
    return kb.as_markup()


def build_slot_keyboard(slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if not slots:
        kb.row(
            InlineKeyboardButton(
                text="На цю дату вільних слотів немає",
                callback_data=NavCB(action="noop_empty").pack(),
            )
        )
        kb.row(InlineKeyboardButton(text="← Інша дата", callback_data=NavCB(action="back").pack()))
        return kb.as_markup()

    morning = sorted([s for s in slots if s.hour < 12])
    afternoon = sorted([s for s in slots if s.hour >= 12])

    if morning:
        kb.row(
            InlineKeyboardButton(
                text="—— До обіду ——",
                callback_data=NavCB(action="noop_header").pack(),
            )
        )
        for chunk in _chunked(morning, 3):
            kb.row(
                *[
                    InlineKeyboardButton(
                        text=s.strftime("%H:%M"),
                        callback_data=SlotCB(time_hhmm=s.hour * 100 + s.minute).pack(),
                    )
                    for s in chunk
                ]
            )

    if afternoon:
        kb.row(
            InlineKeyboardButton(
                text="—— Після обіду ——",
                callback_data=NavCB(action="noop_header").pack(),
            )
        )
        for chunk in _chunked(afternoon, 3):
            kb.row(
                *[
                    InlineKeyboardButton(
                        text=s.strftime("%H:%M"),
                        callback_data=SlotCB(time_hhmm=s.hour * 100 + s.minute).pack(),
                    )
                    for s in chunk
                ]
            )

    kb.row(*_nav_row())
    return kb.as_markup()


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так, підтвердити", callback_data=NavCB(action="confirm"))
    kb.button(text="✖ Скасувати", callback_data=NavCB(action="cancel"))
    kb.adjust(2)
    return kb.as_markup()


def build_back_button() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="← Назад", callback_data=NavCB(action="back"))
    return kb.as_markup()


def build_user_booking_cancel_keyboard(booking_id: str) -> InlineKeyboardMarkup:
    """Single-button inline kb attached to the success message — lets the
    user cancel their freshly-created booking. The handler for this
    callback lives in `bot/handlers/my_bookings.py` (Prompt 5)."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✖ Скасувати запис",
        callback_data=BookingActionCB(booking_id=booking_id, action="cancel"),
    )
    return kb.as_markup()
