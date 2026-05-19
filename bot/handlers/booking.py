"""Booking FSM — service → master → date → slot → contact → confirm.

Atomic confirmation flow (project_specs.md §11):
- Race re-check via calculate_available_slots BEFORE Sheet write.
- Sheet is source of truth: Calendar write failure is logged but doesn't
  roll back the booking.
- Reminders are best-effort: failure logs and continues (the user already
  has the confirmation).

Localized strings (RU per OQ-2) are MSG_* constants at top of file.
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import DateCB, MasterCB, NavCB, ServiceCB, SlotCB
from bot.config import settings
from bot.keyboards.inline import (
    build_confirm_keyboard,
    build_date_keyboard,
    build_master_keyboard,
    build_service_keyboard,
    build_slot_keyboard,
    build_user_booking_cancel_keyboard,
)
from bot.keyboards.reply import main_menu, share_contact
from bot.models import Booking as BookingModel
from bot.models import Master, Service
from bot.services.calendar import CalendarService
from bot.services.phone import normalize_phone
from bot.services.scheduler import schedule_reminder
from bot.services.sheets import SheetsService
from bot.services.slots import calculate_available_slots
from bot.services.whisper import WhisperService
from bot.states import Booking

logger = logging.getLogger(__name__)
booking_router = Router()


# ============================================================================
# User-facing strings (Russian, see OQ-2)
# ============================================================================

MSG_PICK_SERVICE = "Выберите услугу:"
MSG_PICK_MASTER = "Выберите мастера:"
MSG_PICK_DATE = "Выберите дату:"
MSG_PICK_SLOT = "Выберите время:"
MSG_ENTER_NAME = "Как вас зовут? Напишите имя текстом или запишите голосом."
MSG_ENTER_PHONE = "Оставьте номер телефона.\nМожно вручную или через кнопку «Поделиться контактом»."
MSG_VOICE_PROMPT = "🎤 Запишите голосовое сообщение со своим именем."
MSG_VOICE_TOO_LARGE = "Файл слишком большой. Запишите короче или введите имя текстом."
MSG_VOICE_TRANSCRIBE_FAILED = "Не удалось распознать голос. Введите имя текстом."
MSG_VOICE_TRANSCRIBE_EMPTY = "Не удалось распознать чисто. Попробуйте ещё раз или введите текстом."
MSG_VOICE_CONFIRM_TEMPLATE = "Распознано: {name}\n\nПодтвердить или отредактировать?"
MSG_VOICE_NOT_FOR_PHONE = "Для номера используйте цифры или кнопку «Поделиться контактом»."
MSG_VOICE_ONLY_FOR_NAME = "Голосовой ввод — только для имени."
MSG_NO_MASTERS = "Нет доступных мастеров для этой услуги."
MSG_NAME_TOO_SHORT = "Имя слишком короткое. Введите ещё раз."
MSG_INVALID_PHONE = (
    "Не получилось распознать номер. Попробуйте ещё раз "
    "или нажмите кнопку «Поделиться контактом»."
)
MSG_DAY_UNAVAILABLE = "Этот день недоступен"
MSG_SLOT_TAKEN = "Этот слот только что заняли, выберите другой:"
MSG_GENERIC_ERROR = "Что-то пошло не так. Попробуйте ещё раз позже."
MSG_CANCELLED = "Запись отменена."
MSG_MAIN_MENU = "Главное меню:"
MSG_CALENDAR_PENDING_NOTE = "\n\n⚠ Calendar event will be created on the next sync attempt."

MSG_CONFIRM_TEMPLATE = (
    "Подтвердите запись:\n\n"
    "📋 {service_name}\n"
    "💇 {master_name}\n"
    "📅 {date_str}\n"
    "⏰ {time_str}\n"
    "👤 {client_name}\n"
    "📱 {client_phone}\n\n"
    "Всё верно?"
)
MSG_SUCCESS_TEMPLATE = (
    "✅ Запись создана!\n\n"
    "📋 {service_name}\n"
    "💇 {master_name}\n"
    "📅 {date_str} в {time_str}\n\n"
    "Мы отправим напоминания за 24 часа и за 1 час до визита."
)
MSG_OWNER_NEW_BOOKING_TEMPLATE = (
    "🆕 Новая запись:\n\n"
    "👤 {client_name}\n"
    "📱 {client_phone}\n"
    "📋 {service_name}\n"
    "💇 {master_name}\n"
    "📅 {date_str} {time_str}\n"
    "🆔 {booking_id}"
)


ALL_BOOKING_STATES = (
    Booking.choosing_service,
    Booking.choosing_master,
    Booking.choosing_date,
    Booking.choosing_slot,
    Booking.entering_contact,
    Booking.confirming,
)


# ============================================================================
# Helpers
# ============================================================================


async def _service_by_id(sheets: SheetsService, service_id: str) -> Service | None:
    for s in await sheets.load_services():
        if s.id == service_id:
            return s
    return None


async def _master_by_id(sheets: SheetsService, master_id: str) -> Master | None:
    for m in await sheets.load_masters():
        if m.id == master_id:
            return m
    return None


async def _eligible_masters(sheets: SheetsService, service: Service) -> list[Master]:
    masters = [m for m in await sheets.load_masters() if m.is_active]
    if service.master_ids:
        eligible_ids = set(service.master_ids)
        masters = [m for m in masters if m.id in eligible_ids]
    return masters


async def _compute_available_slots(
    sheets: SheetsService,
    calendar: CalendarService,
    master: Master,
    service: Service,
    picked: date,
) -> list[datetime]:
    bookings_today = await sheets.load_bookings_for_master_date(master.id, picked)
    blackouts = await sheets.load_blackouts_for_date(picked)
    busy = await calendar.query_busy_intervals(master.calendar_id, picked)
    slots = calculate_available_slots(master, picked, service, bookings_today, blackouts, busy)
    now = datetime.now()
    if picked == now.date():
        slots = [s for s in slots if s > now]
    return slots


async def _safe_edit(
    query: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            logger.exception("edit_text failed; falling back to send")
            if query.bot is not None:
                await query.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=text,
                    reply_markup=reply_markup,
                )


def _voice_button_kb() -> InlineKeyboardMarkup:
    """Single-button inline keyboard offering voice input on the name prompt."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🎤 Голосом", callback_data=NavCB(action="voice_input").pack())
    return kb.as_markup()


async def _show_confirmation(
    out: Message,
    state: FSMContext,
    sheets: SheetsService,
) -> None:
    data = await state.get_data()
    service = await _service_by_id(sheets, str(data.get("service_id", "")))
    master = await _master_by_id(sheets, str(data.get("master_id", "")))
    iso_dt = str(data.get("iso_datetime", ""))
    if service is None or master is None or not iso_dt:
        await out.answer(MSG_GENERIC_ERROR, reply_markup=main_menu())
        await state.clear()
        return

    start = datetime.fromisoformat(iso_dt)
    text = MSG_CONFIRM_TEMPLATE.format(
        service_name=service.name,
        master_name=master.name,
        date_str=start.strftime("%d.%m.%Y"),
        time_str=start.strftime("%H:%M"),
        client_name=str(data.get("client_name", "")),
        client_phone=str(data.get("client_phone", "")),
    )
    await state.set_state(Booking.confirming)
    await out.answer(text, reply_markup=build_confirm_keyboard())


# ============================================================================
# /cancel + NavCB cancel / back / noop
# ============================================================================


@booking_router.message(Command("cancel"), StateFilter(*ALL_BOOKING_STATES))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MSG_CANCELLED, reply_markup=main_menu())


@booking_router.callback_query(
    NavCB.filter(F.action == "cancel"),
    StateFilter(*ALL_BOOKING_STATES),
)
async def on_nav_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit(query, MSG_CANCELLED)
    if isinstance(query.message, Message):
        await query.message.answer(MSG_MAIN_MENU, reply_markup=main_menu())
    await query.answer()


@booking_router.callback_query(NavCB.filter(F.action == "noop_date"))
async def on_noop_date(query: CallbackQuery) -> None:
    await query.answer(MSG_DAY_UNAVAILABLE)


@booking_router.callback_query(NavCB.filter(F.action == "noop_header"))
async def on_noop_header(query: CallbackQuery) -> None:
    await query.answer()


@booking_router.callback_query(NavCB.filter(F.action == "noop_empty"))
async def on_noop_empty(query: CallbackQuery) -> None:
    await query.answer()


@booking_router.callback_query(
    NavCB.filter(F.action == "back"),
    StateFilter(*ALL_BOOKING_STATES),
)
async def on_nav_back(
    query: CallbackQuery,
    state: FSMContext,
    sheets: SheetsService,
    calendar: CalendarService,
) -> None:
    current = await state.get_state()
    data = await state.get_data()

    if current == Booking.choosing_master.state:
        await state.set_state(Booking.choosing_service)
        services = await sheets.load_services()
        await _safe_edit(query, MSG_PICK_SERVICE, build_service_keyboard(services))
    elif current == Booking.choosing_date.state:
        service = await _service_by_id(sheets, str(data.get("service_id", "")))
        if service is None:
            await state.clear()
            await query.answer()
            return
        masters = await _eligible_masters(sheets, service)
        if len(masters) <= 1:
            await state.set_state(Booking.choosing_service)
            services = await sheets.load_services()
            await _safe_edit(query, MSG_PICK_SERVICE, build_service_keyboard(services))
        else:
            await state.set_state(Booking.choosing_master)
            await _safe_edit(query, MSG_PICK_MASTER, build_master_keyboard(masters, service))
    elif current == Booking.choosing_slot.state:
        master = await _master_by_id(sheets, str(data.get("master_id", "")))
        if master is None:
            await state.clear()
            await query.answer()
            return
        await state.set_state(Booking.choosing_date)
        blackouts = await sheets.load_all_blackouts()
        await _safe_edit(
            query,
            MSG_PICK_DATE,
            build_date_keyboard(date.today(), master, blackouts),
        )
    elif current == Booking.entering_contact.state:
        master = await _master_by_id(sheets, str(data.get("master_id", "")))
        service = await _service_by_id(sheets, str(data.get("service_id", "")))
        iso_date_str = str(data.get("iso_date", ""))
        if master is None or service is None or not iso_date_str:
            await state.clear()
            await query.answer()
            return
        new_data = {
            k: v
            for k, v in data.items()
            if k not in ("client_name", "client_phone", "iso_datetime")
        }
        await state.set_data(new_data)
        await state.set_state(Booking.choosing_slot)
        picked = date.fromisoformat(iso_date_str)
        slots = await _compute_available_slots(sheets, calendar, master, service, picked)
        await _safe_edit(query, MSG_PICK_SLOT, build_slot_keyboard(slots))
    elif current == Booking.confirming.state:
        new_data = {k: v for k, v in data.items() if k != "client_phone"}
        await state.set_data(new_data)
        await state.set_state(Booking.entering_contact)
        if isinstance(query.message, Message):
            await query.message.answer(MSG_ENTER_PHONE, reply_markup=share_contact())
    await query.answer()


# ============================================================================
# Service / Master / Date / Slot pick
# ============================================================================


@booking_router.callback_query(
    ServiceCB.filter(),
    StateFilter(Booking.choosing_service),
)
async def on_service_pick(
    query: CallbackQuery,
    callback_data: ServiceCB,
    state: FSMContext,
    sheets: SheetsService,
) -> None:
    service = await _service_by_id(sheets, callback_data.service_id)
    if service is None:
        await query.answer("Услуга не найдена", show_alert=True)
        return
    await state.update_data(service_id=service.id)

    masters = await _eligible_masters(sheets, service)
    if not masters:
        await query.answer(MSG_NO_MASTERS, show_alert=True)
        return

    blackouts = await sheets.load_all_blackouts()
    if len(masters) == 1:
        await state.update_data(master_id=masters[0].id)
        await state.set_state(Booking.choosing_date)
        await _safe_edit(
            query,
            MSG_PICK_DATE,
            build_date_keyboard(date.today(), masters[0], blackouts),
        )
    else:
        await state.set_state(Booking.choosing_master)
        await _safe_edit(query, MSG_PICK_MASTER, build_master_keyboard(masters, service))
    await query.answer()


@booking_router.callback_query(
    MasterCB.filter(),
    StateFilter(Booking.choosing_master),
)
async def on_master_pick(
    query: CallbackQuery,
    callback_data: MasterCB,
    state: FSMContext,
    sheets: SheetsService,
) -> None:
    master = await _master_by_id(sheets, callback_data.master_id)
    if master is None:
        await query.answer("Мастер не найден", show_alert=True)
        return
    await state.update_data(master_id=master.id)
    await state.set_state(Booking.choosing_date)
    blackouts = await sheets.load_all_blackouts()
    await _safe_edit(query, MSG_PICK_DATE, build_date_keyboard(date.today(), master, blackouts))
    await query.answer()


@booking_router.callback_query(
    DateCB.filter(),
    StateFilter(Booking.choosing_date),
)
async def on_date_pick(
    query: CallbackQuery,
    callback_data: DateCB,
    state: FSMContext,
    sheets: SheetsService,
    calendar: CalendarService,
) -> None:
    picked = date.fromisoformat(callback_data.iso_date)
    data = await state.get_data()
    master = await _master_by_id(sheets, str(data.get("master_id", "")))
    service = await _service_by_id(sheets, str(data.get("service_id", "")))
    if master is None or service is None:
        await query.answer(MSG_GENERIC_ERROR, show_alert=True)
        return

    slots = await _compute_available_slots(sheets, calendar, master, service, picked)
    await state.update_data(iso_date=picked.isoformat())
    await state.set_state(Booking.choosing_slot)
    await _safe_edit(query, MSG_PICK_SLOT, build_slot_keyboard(slots))
    await query.answer()


@booking_router.callback_query(
    SlotCB.filter(),
    StateFilter(Booking.choosing_slot),
)
async def on_slot_pick(
    query: CallbackQuery,
    callback_data: SlotCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    iso_date_str = str(data.get("iso_date", ""))
    if not iso_date_str:
        await query.answer(MSG_GENERIC_ERROR, show_alert=True)
        return
    d = date.fromisoformat(iso_date_str)
    hh, mm = divmod(callback_data.time_hhmm, 100)
    chosen = datetime.combine(d, datetime.min.time()).replace(hour=hh, minute=mm)
    await state.update_data(iso_datetime=chosen.isoformat())
    await state.set_state(Booking.entering_contact)
    await _safe_edit(query, MSG_ENTER_NAME, _voice_button_kb())
    await query.answer()


# ============================================================================
# Contact entry (sub-step disambiguated via FSM data)
# ============================================================================


@booking_router.message(StateFilter(Booking.entering_contact), F.text)
async def on_contact_text(message: Message, state: FSMContext, sheets: SheetsService) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()

    if "client_name" not in data:
        if len(raw) < 2:
            await message.answer(MSG_NAME_TOO_SHORT)
            return
        await state.update_data(client_name=raw)
        await message.answer(MSG_ENTER_PHONE, reply_markup=share_contact())
        return

    phone = normalize_phone(raw)
    if phone is None:
        await message.answer(MSG_INVALID_PHONE)
        return
    await state.update_data(client_phone=phone)
    await message.answer("Принято.", reply_markup=main_menu())
    await _show_confirmation(message, state, sheets)


@booking_router.message(StateFilter(Booking.entering_contact), F.contact)
async def on_contact_share(message: Message, state: FSMContext, sheets: SheetsService) -> None:
    contact = message.contact
    if contact is None:
        await message.answer(MSG_INVALID_PHONE)
        return
    data = await state.get_data()
    raw_phone = contact.phone_number or ""
    normalized = normalize_phone(raw_phone) or raw_phone

    if "client_name" not in data:
        fallback_name = (contact.first_name or "Клиент").strip()
        await state.update_data(client_name=fallback_name, client_phone=normalized)
    else:
        await state.update_data(client_phone=normalized)

    await message.answer("Принято.", reply_markup=main_menu())
    await _show_confirmation(message, state, sheets)


# ============================================================================
# Voice name input (WOW 3 — Groq Whisper)
# ============================================================================


@booking_router.callback_query(
    NavCB.filter(F.action == "voice_input"),
    StateFilter(Booking.entering_contact),
)
async def on_voice_input(query: CallbackQuery, state: FSMContext) -> None:
    """User tapped 🎤 Голосом — switch the prompt to voice-record instructions."""
    data = await state.get_data()
    if "client_name" in data:
        await query.answer(MSG_VOICE_ONLY_FOR_NAME, show_alert=True)
        return
    await _safe_edit(query, MSG_VOICE_PROMPT)
    await query.answer()


@booking_router.message(StateFilter(Booking.entering_contact), F.voice)
async def on_contact_voice(
    message: Message,
    state: FSMContext,
    bot: Bot,
    sheets: SheetsService,
    whisper: WhisperService,
) -> None:
    """Transcribe voice → name. Soft failures stay in state; hard API failures
    also log to _errors. Voice is only valid for the name sub-step; if the
    user already entered name and is at the phone sub-step, redirect them.
    """
    if message.voice is None or message.from_user is None:
        return
    data = await state.get_data()
    if "client_name" in data:
        await message.answer(MSG_VOICE_NOT_FOR_PHONE, reply_markup=share_contact())
        return

    # 1 MB cap — anything bigger than a name clip is suspicious (§9.4).
    if message.voice.file_size and message.voice.file_size > 1_000_000:
        await message.answer(MSG_VOICE_TOO_LARGE)
        return

    try:
        voice_file = await bot.download(message.voice.file_id)
        if voice_file is None:
            raise RuntimeError("bot.download returned None")
        file_bytes = voice_file.read()
        name = await whisper.transcribe(file_bytes, language="ru")
    except Exception as exc:
        logger.warning("Voice transcribe hard-fail: %s", exc)
        await _log_error_safe(
            sheets,
            handler="booking.on_contact_voice.transcribe",
            user_id=message.from_user.id,
            error_text=f"whisper.transcribe failed: {type(exc).__name__}: {exc}",
            payload={"file_size": message.voice.file_size},
        )
        await message.answer(MSG_VOICE_TRANSCRIBE_FAILED)
        return

    if not name or len(name) > 50:
        logger.info("Voice transcribe soft-skip (empty or too long): %r", name)
        await message.answer(MSG_VOICE_TRANSCRIBE_EMPTY)
        return

    # Pending name lives in FSM data — callback_data 64-byte limit would
    # truncate longer names if we tried to round-trip via callback payload.
    await state.update_data(pending_voice_name=name)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=NavCB(action="voice_confirm").pack())
    kb.button(text="✏️ Редактировать", callback_data=NavCB(action="voice_edit").pack())
    kb.adjust(2)
    await message.answer(
        MSG_VOICE_CONFIRM_TEMPLATE.format(name=name),
        reply_markup=kb.as_markup(),
    )


@booking_router.callback_query(
    NavCB.filter(F.action == "voice_confirm"),
    StateFilter(Booking.entering_contact),
)
async def on_voice_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """User accepted the transcribed name → save it and advance to phone step."""
    data = await state.get_data()
    name = str(data.get("pending_voice_name", "")).strip()
    if not name:
        await query.answer(MSG_GENERIC_ERROR, show_alert=True)
        return
    await state.update_data(client_name=name, pending_voice_name=None)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(f"Имя: {name}")
        except Exception:
            logger.exception("voice_confirm edit_text failed")
        await query.message.answer(MSG_ENTER_PHONE, reply_markup=share_contact())
    await query.answer()


@booking_router.callback_query(
    NavCB.filter(F.action == "voice_edit"),
    StateFilter(Booking.entering_contact),
)
async def on_voice_edit(query: CallbackQuery, state: FSMContext) -> None:
    """User rejected the transcription → revert to the name prompt + voice button."""
    await state.update_data(pending_voice_name=None)
    await _safe_edit(query, MSG_ENTER_NAME, _voice_button_kb())
    await query.answer()


# ============================================================================
# Confirmation — atomic write flow
# ============================================================================


@booking_router.callback_query(
    NavCB.filter(F.action == "confirm"),
    StateFilter(Booking.confirming),
)
async def on_confirm(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    sheets: SheetsService,
    calendar: CalendarService,
) -> None:
    if query.from_user is None:
        await query.answer(MSG_GENERIC_ERROR, show_alert=True)
        return
    data = await state.get_data()
    service = await _service_by_id(sheets, str(data.get("service_id", "")))
    master = await _master_by_id(sheets, str(data.get("master_id", "")))
    iso_dt = str(data.get("iso_datetime", ""))
    client_name = str(data.get("client_name", ""))
    client_phone = str(data.get("client_phone", ""))
    if service is None or master is None or not iso_dt or not client_name or not client_phone:
        await query.answer(MSG_GENERIC_ERROR, show_alert=True)
        return

    start = datetime.fromisoformat(iso_dt)
    end = start + timedelta(minutes=service.duration_min)
    picked = start.date()

    # === Step 1: Race re-check ===
    fresh = await _compute_available_slots(sheets, calendar, master, service, picked)
    if start not in fresh:
        await state.set_state(Booking.choosing_slot)
        await _safe_edit(query, MSG_SLOT_TAKEN, build_slot_keyboard(fresh))
        await query.answer()
        return

    # === Step 2: Build booking ===
    booking_id = str(uuid.uuid4())
    booking = BookingModel(
        id=booking_id,
        client_telegram_id=query.from_user.id,
        client_name=client_name,
        client_phone=client_phone,
        service_id=service.id,
        master_id=master.id,
        datetime_start=start,
        datetime_end=end,
        status="confirmed",
        created_at=datetime.now(),
    )

    # === Step 3: Write Sheet (source of truth) ===
    try:
        await sheets.append_booking(booking)
    except Exception:
        logger.exception("append_booking failed for booking %s", booking_id)
        await _safe_edit(query, MSG_GENERIC_ERROR)
        if isinstance(query.message, Message):
            await query.message.answer(MSG_MAIN_MENU, reply_markup=main_menu())
        await state.clear()
        await query.answer()
        return

    # === Step 4: Calendar event (best effort) ===
    calendar_pending = ""
    try:
        event_id = await calendar.create_event(master.calendar_id, booking)
        await sheets.update_booking_status(booking_id, "confirmed", calendar_event_id=event_id)
    except Exception:
        logger.exception("create_event failed for booking %s", booking_id)
        await _log_error_safe(
            sheets,
            handler="booking.on_confirm.create_event",
            user_id=query.from_user.id,
            error_text="calendar.create_event failed",
            payload={
                "booking_id": booking_id,
                "master_calendar_id": master.calendar_id,
            },
        )
        calendar_pending = MSG_CALENDAR_PENDING_NOTE

    # === Step 5: Schedule reminders (best effort) ===
    now = datetime.now()
    for hours in (24, 1):
        fire_at = start - timedelta(hours=hours)
        if fire_at <= now:
            continue
        try:
            await schedule_reminder(booking_id, fire_at, hours)
        except Exception:
            logger.exception(
                "schedule_reminder failed for booking=%s kind=%dh",
                booking_id,
                hours,
            )

    # === Step 6: User confirmation message ===
    success_text = MSG_SUCCESS_TEMPLATE.format(
        service_name=service.name,
        master_name=master.name,
        date_str=start.strftime("%d.%m.%Y"),
        time_str=start.strftime("%H:%M"),
    )
    await _safe_edit(query, success_text, build_user_booking_cancel_keyboard(booking_id))

    # === Step 7: Owner notification (rate-limit hygiene per §3.7) ===
    await asyncio.sleep(0.05)
    owner_text = MSG_OWNER_NEW_BOOKING_TEMPLATE.format(
        client_name=client_name,
        client_phone=client_phone,
        service_name=service.name,
        master_name=master.name,
        date_str=start.strftime("%d.%m.%Y"),
        time_str=start.strftime("%H:%M"),
        booking_id=booking_id,
    )
    if calendar_pending:
        owner_text += calendar_pending
    try:
        await bot.send_message(chat_id=settings.owner_telegram_chat_id, text=owner_text)
    except Exception:
        logger.exception("Owner notification failed for booking %s", booking_id)

    # === Step 8: Clear state ===
    await state.clear()
    await query.answer()


async def _log_error_safe(
    sheets: SheetsService,
    handler: str,
    user_id: int,
    error_text: str,
    payload: dict[str, Any],
) -> None:
    """Wrap sheets.log_error so a Sheet write failure inside the error
    handler itself doesn't propagate. The full traceback is already in
    the standard logger; the Sheet row is the human-readable audit."""
    try:
        await sheets.log_error(handler, user_id, error_text, payload)
    except Exception:
        logger.exception("Failed to log error to Sheet (handler=%s)", handler)
