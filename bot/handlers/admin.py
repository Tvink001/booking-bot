"""Admin commands: /today, /week, /stats, /export.

Gated by `AdminFilter` (user_id ∈ settings.admin_telegram_ids). Non-admins
who type one of these commands get a single short reply and the handler
returns — implemented via a separate fallback handler that matches the
same commands without the filter (aiogram routes by order: admin handler
first, non-admin fallback second).
"""

import csv
import io
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, Filter
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import NavCB
from bot.config import settings
from bot.models import Booking, Master, Service
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)
admin_router = Router()

_ADMIN_COMMANDS = ["today", "week", "stats", "export"]

MSG_NO_RIGHTS = "У вас нет прав на эту команду."
MSG_TODAY_NONE = "На сегодня ({date_str}) записей нет."
MSG_WEEK_NONE = "На ближайшие 7 дней записей нет."


class AdminFilter(Filter):
    """Filter passing only users whose telegram ID is in `admin_ids`.

    `admin_ids` defaults to `settings.admin_telegram_ids` at instantiation
    time; tests can pass an explicit list to avoid coupling to env state.
    """

    def __init__(self, admin_ids: list[int] | None = None) -> None:
        self.admin_ids: list[int] = (
            admin_ids if admin_ids is not None else settings.admin_telegram_ids
        )

    async def __call__(self, event: Message) -> bool:
        if event.from_user is None:
            return False
        return event.from_user.id in self.admin_ids


# ============================================================================
# Admin entry point — single dispatcher for all 4 commands
# ============================================================================


@admin_router.message(Command(commands=_ADMIN_COMMANDS), AdminFilter())
async def on_admin_command(message: Message, bot: Bot, sheets: SheetsService) -> None:
    cmd = (message.text or "").split(maxsplit=1)[0].lstrip("/").lower()
    if cmd == "today":
        await _do_today(message, sheets)
    elif cmd == "week":
        await _do_week(message, sheets)
    elif cmd == "stats":
        await _do_stats(message, sheets)
    elif cmd == "export":
        await _do_export(message, bot, sheets, all_time=False)


@admin_router.message(Command(commands=_ADMIN_COMMANDS))
async def on_admin_command_denied(message: Message) -> None:
    """Fallback: non-admin attempted an admin command (didn't match the
    AdminFilter-gated handler above)."""
    await message.answer(MSG_NO_RIGHTS)


@admin_router.callback_query(NavCB.filter(F.action == "export_all"))
async def on_export_all(query: CallbackQuery, bot: Bot, sheets: SheetsService) -> None:
    """Inline 'Все записи' button on the /export reply — re-run with no date filter."""
    if query.from_user is None or query.from_user.id not in settings.admin_telegram_ids:
        await query.answer(MSG_NO_RIGHTS, show_alert=True)
        return
    if isinstance(query.message, Message):
        await _do_export(query.message, bot, sheets, all_time=True)
    await query.answer()


# ============================================================================
# Command implementations
# ============================================================================


async def _do_today(message: Message, sheets: SheetsService) -> None:
    today = date.today()
    all_b = await sheets.load_all_bookings()
    masters = await sheets.load_masters()
    services = {s.id: s for s in await sheets.load_services()}

    todays = [b for b in all_b if b.datetime_start.date() == today and b.status == "confirmed"]
    if not todays:
        await message.answer(MSG_TODAY_NONE.format(date_str=today.strftime("%d.%m.%Y")))
        return

    for master_id, bookings in _group_by_master(todays).items():
        master_name = _name_of(masters, master_id)
        lines = [f"📅 {master_name} — сегодня ({today.strftime('%d.%m.%Y')}):"]
        for b in sorted(bookings, key=lambda x: x.datetime_start):
            lines.append(_booking_line(b, services))
        await message.answer("\n".join(lines))


async def _do_week(message: Message, sheets: SheetsService) -> None:
    today = date.today()
    week_end = today + timedelta(days=7)
    all_b = await sheets.load_all_bookings()
    masters = await sheets.load_masters()
    services = {s.id: s for s in await sheets.load_services()}

    week_bookings = [
        b for b in all_b if today <= b.datetime_start.date() < week_end and b.status == "confirmed"
    ]
    if not week_bookings:
        await message.answer(MSG_WEEK_NONE)
        return

    for master_id, bookings in _group_by_master(week_bookings).items():
        master_name = _name_of(masters, master_id)
        lines = [f"📅 {master_name} — ближайшие 7 дней:"]
        for b in sorted(bookings, key=lambda x: x.datetime_start):
            lines.append(
                f"• {b.datetime_start.strftime('%d.%m %H:%M')} — "
                f"{b.client_name} ({_service_name(b.service_id, services)})"
            )
        await message.answer("\n".join(lines))


async def _do_stats(message: Message, sheets: SheetsService) -> None:
    now = datetime.now()
    month_start = date(now.year, now.month, 1)
    if now.month == 12:
        month_end = date(now.year + 1, 1, 1)
    else:
        month_end = date(now.year, now.month + 1, 1)

    all_b = await sheets.load_all_bookings()
    in_month = [b for b in all_b if month_start <= b.datetime_start.date() < month_end]

    counts: dict[str, int] = defaultdict(int)
    for b in in_month:
        counts[b.status] += 1

    text = (
        f"📊 Статистика за {month_start.strftime('%m.%Y')}\n\n"
        f"• Подтверждённых: {counts.get('confirmed', 0)}\n"
        f"• Отменённых: {counts.get('cancelled', 0)}\n"
        f"• Завершённых: {counts.get('completed', 0)}\n"
        f"• Не пришли: {counts.get('no_show', 0)}\n\n"
        f"Всего: {len(in_month)}"
    )
    await message.answer(text)


async def _do_export(message: Message, bot: Bot, sheets: SheetsService, *, all_time: bool) -> None:
    all_b = await sheets.load_all_bookings()

    if all_time:
        scope_bookings = list(all_b)
        period_label = "all-time"
        filename = "bookings-all.csv"
        caption = f"Экспорт всех записей ({len(scope_bookings)})"
    else:
        now = datetime.now()
        month_start = date(now.year, now.month, 1)
        if now.month == 12:
            month_end = date(now.year + 1, 1, 1)
        else:
            month_end = date(now.year, now.month + 1, 1)
        scope_bookings = [b for b in all_b if month_start <= b.datetime_start.date() < month_end]
        period_label = month_start.strftime("%Y-%m")
        filename = f"bookings-{period_label}.csv"
        caption = f"Экспорт за {month_start.strftime('%m.%Y')} ({len(scope_bookings)})"

    scope_bookings.sort(key=lambda b: b.datetime_start)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "client_telegram_id",
            "client_name",
            "client_phone",
            "service_id",
            "master_id",
            "datetime_start",
            "datetime_end",
            "status",
            "calendar_event_id",
            "created_at",
            "cancelled_at",
        ]
    )
    for b in scope_bookings:
        writer.writerow(
            [
                b.id,
                b.client_telegram_id,
                b.client_name,
                b.client_phone,
                b.service_id,
                b.master_id,
                b.datetime_start.isoformat(),
                b.datetime_end.isoformat(),
                b.status,
                b.calendar_event_id or "",
                b.created_at.isoformat(),
                b.cancelled_at.isoformat() if b.cancelled_at else "",
            ]
        )

    # UTF-8 BOM so Excel detects encoding correctly.
    file_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    document = BufferedInputFile(file=file_bytes, filename=filename)

    if not all_time:
        kb = InlineKeyboardBuilder()
        kb.button(text="📦 Все записи", callback_data=NavCB(action="export_all"))
        markup = kb.as_markup()
    else:
        markup = None

    await bot.send_document(
        chat_id=message.chat.id,
        document=document,
        caption=caption,
        reply_markup=markup,
    )


# ============================================================================
# Formatters
# ============================================================================


def _group_by_master(bookings: list[Booking]) -> dict[str, list[Booking]]:
    grouped: dict[str, list[Booking]] = defaultdict(list)
    for b in bookings:
        grouped[b.master_id].append(b)
    return grouped


def _name_of(masters: list[Master], master_id: str) -> str:
    return next((m.name for m in masters if m.id == master_id), master_id)


def _service_name(service_id: str, services: dict[str, Service]) -> str:
    return services[service_id].name if service_id in services else service_id


def _booking_line(b: Booking, services: dict[str, Service]) -> str:
    return (
        f"• {b.datetime_start.strftime('%H:%M')} — "
        f"{b.client_name} ({_service_name(b.service_id, services)}) "
        f"📞 {b.client_phone}"
    )
