"""'📋 Мои записи' view + cancellation flow.

Cancellation strictly follows the write-after-success discipline from
project_specs.md §12 invariants. The user's view is built from a single
load_all_bookings_for_client call; cancellation goes:

    1. scheduler.cancel_reminders(booking_id)
    2. calendar.delete_event(master.calendar_id, booking.calendar_event_id)
       (404 treated as already-deleted ⇒ success)
    3. sheets.update_booking_status(id, 'cancelled', cancelled_at=now)
    4. notify master via DM (best-effort)
    5. edit user-facing message → "Запис скасовано"

Only step 3 makes the booking officially cancelled. Failures before
step 3 keep the row in status='confirmed' — the user can retry.
"""

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import BookingActionCB
from bot.services.calendar import CalendarService
from bot.services.scheduler import cancel_reminders
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)
my_bookings_router = Router()


MSG_NO_BOOKINGS = "You have no upcoming bookings."
MSG_BOOKING_NOT_FOUND = "Booking not found"
MSG_ALREADY_CANCELLED = "Booking is already cancelled or completed"
MSG_CANCELLED_USER = "✅ Booking cancelled."
MSG_CANCEL_GENERIC_ERROR = "Couldn't cancel the booking. Please try later."
MSG_MASTER_CANCELLED_TEMPLATE = (
    "❌ Booking cancelled by client:\n"
    "👤 {client_name}\n"
    "📅 {date_str} {time_str}\n"
    "🆔 {booking_id}"
)
MSG_BOOKING_ROW_TEMPLATE = "📅 {date_str} at {time_str}\n💇 {master_name}\n📋 {service_name}"


@my_bookings_router.message(F.text == "📋 My bookings")
async def cmd_my_bookings(message: Message, state: FSMContext, sheets: SheetsService) -> None:
    if message.from_user is None:
        return
    await state.clear()  # defense against tapping mid-flow
    user_id = message.from_user.id

    bookings = await sheets.load_all_bookings_for_client(user_id)
    now = datetime.now()
    upcoming = sorted(
        [b for b in bookings if b.status == "confirmed" and b.datetime_start > now],
        key=lambda b: b.datetime_start,
    )

    if not upcoming:
        await message.answer(MSG_NO_BOOKINGS)
        return

    masters = {m.id: m for m in await sheets.load_masters()}
    services = {s.id: s for s in await sheets.load_services()}

    for booking in upcoming:
        master_name = (
            masters[booking.master_id].name if booking.master_id in masters else booking.master_id
        )
        service_name = (
            services[booking.service_id].name
            if booking.service_id in services
            else booking.service_id
        )
        text = MSG_BOOKING_ROW_TEMPLATE.format(
            date_str=booking.datetime_start.strftime("%d.%m.%Y"),
            time_str=booking.datetime_start.strftime("%H:%M"),
            master_name=master_name,
            service_name=service_name,
        )
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✖ Cancel",
            callback_data=BookingActionCB(booking_id=booking.id, action="cancel"),
        )
        await message.answer(text, reply_markup=kb.as_markup())


@my_bookings_router.callback_query(BookingActionCB.filter(F.action == "cancel"))
async def on_cancel_booking(
    query: CallbackQuery,
    callback_data: BookingActionCB,
    bot: Bot,
    sheets: SheetsService,
    calendar: CalendarService,
) -> None:
    """Cancel a booking. Order matters — see module docstring + §12 invariants."""
    if query.from_user is None:
        await query.answer(MSG_CANCEL_GENERIC_ERROR, show_alert=True)
        return

    user_id = query.from_user.id
    booking_id = callback_data.booking_id

    # Load booking owned by this user. Defense against forged callback_data.
    bookings = await sheets.load_all_bookings_for_client(user_id)
    booking = next((b for b in bookings if b.id == booking_id), None)
    if booking is None:
        await query.answer(MSG_BOOKING_NOT_FOUND, show_alert=True)
        return
    if booking.status != "confirmed":
        await query.answer(MSG_ALREADY_CANCELLED, show_alert=True)
        return

    # Load master once for both delete_event and DM notify
    masters = await sheets.load_masters()
    master = next((m for m in masters if m.id == booking.master_id), None)

    # === Step 1: Cancel reminders ===
    try:
        await cancel_reminders(booking_id)
    except Exception:
        logger.exception("cancel_reminders failed for booking %s", booking_id)
        # Continue: even if APScheduler is misbehaving, the reminder fires
        # will skip on status != 'confirmed' check (Prompt 6 idempotency).

    # === Step 2: Delete Calendar event (404 = already gone = success) ===
    if booking.calendar_event_id and master is not None:
        try:
            await calendar.delete_event(master.calendar_id, booking.calendar_event_id)
        except Exception as exc:
            err_text = str(exc).lower()
            if "404" in err_text or "not found" in err_text or "has been deleted" in err_text:
                logger.info(
                    "Calendar event %s already gone — treat as success",
                    booking.calendar_event_id,
                )
            else:
                logger.exception("delete_event failed for booking %s (continuing)", booking_id)

    # === Step 3: Flip Sheet status — this is the canonical cancellation ===
    try:
        await sheets.update_booking_status(
            booking_id,
            "cancelled",
            cancelled_at=datetime.now().isoformat(),
        )
    except Exception:
        logger.exception(
            "Sheet status update failed for booking %s — booking stays confirmed",
            booking_id,
        )
        await query.answer(MSG_CANCEL_GENERIC_ERROR, show_alert=True)
        return

    # === Step 4: Notify master (best-effort) ===
    if master is not None and master.telegram_id:
        text = MSG_MASTER_CANCELLED_TEMPLATE.format(
            client_name=booking.client_name,
            date_str=booking.datetime_start.strftime("%d.%m.%Y"),
            time_str=booking.datetime_start.strftime("%H:%M"),
            booking_id=booking_id,
        )
        try:
            await bot.send_message(chat_id=master.telegram_id, text=text)
        except Exception:
            logger.exception(
                "Master DM failed for booking %s (best-effort, continuing)",
                booking_id,
            )

    # === Step 5: Confirm to user ===
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(MSG_CANCELLED_USER)
        except Exception:
            logger.exception("edit_text failed on cancel confirmation")
    await query.answer()
