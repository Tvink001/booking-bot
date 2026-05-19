"""Cancellation order test — locks in the write-after-success discipline.

The booking lifecycle invariant from project_specs.md §12: side effects on
external state (reminders, calendar) happen BEFORE the Sheet status flip.
If a side effect fails, the row stays 'confirmed' and the user can retry.
This test asserts the exact call order on the canonical happy path.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from bot.callbacks import BookingActionCB
from bot.handlers.my_bookings import on_cancel_booking
from bot.models import Booking, Master


@pytest.fixture
def confirmed_booking() -> Booking:
    start = datetime.now() + timedelta(days=2)
    return Booking(
        id="bk-1",
        client_telegram_id=123,
        client_name="Тест",
        client_phone="+380501234567",
        service_id="haircut-30",
        master_id="m1",
        datetime_start=start,
        datetime_end=start + timedelta(minutes=30),
        status="confirmed",
        created_at=datetime.now(),
        calendar_event_id="evt-abc",
    )


@pytest.fixture
def master_with_telegram() -> Master:
    return Master(
        id="m1",
        name="Майстер",
        telegram_id=555,
        calendar_id="m1@example.com",
        work_hours="10:00-19:00",
        work_days=[1, 2, 3, 4, 5],
        is_active=True,
    )


async def test_cancel_call_order_matches_invariant(
    confirmed_booking: Booking, master_with_telegram: Master
) -> None:
    """Asserts: cancel_reminders → delete_event → sheets.update → master DM → edit."""
    recorder: list[str] = []

    sheets = MagicMock()
    sheets.load_all_bookings_for_client = AsyncMock(return_value=[confirmed_booking])
    sheets.load_masters = AsyncMock(return_value=[master_with_telegram])
    sheets.update_booking_status = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("sheets.update_booking_status")
    )

    calendar = MagicMock()
    calendar.delete_event = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("calendar.delete_event")
    )

    bot = MagicMock()
    bot.send_message = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("bot.send_message_master")
    )

    query = MagicMock()
    query.from_user = MagicMock(id=123)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("query.message.edit_text")
    )
    query.answer = AsyncMock()

    callback_data = BookingActionCB(booking_id="bk-1", action="cancel")

    with patch(
        "bot.handlers.my_bookings.cancel_reminders",
        new=AsyncMock(side_effect=lambda *a, **kw: recorder.append("scheduler.cancel_reminders")),
    ):
        await on_cancel_booking(query, callback_data, bot, sheets, calendar)

    assert recorder == [
        "scheduler.cancel_reminders",
        "calendar.delete_event",
        "sheets.update_booking_status",
        "bot.send_message_master",
        "query.message.edit_text",
    ]


async def test_cancel_rejects_non_owner(confirmed_booking: Booking) -> None:
    """Defense against forged callback_data: only the booking's owner can cancel."""
    sheets = MagicMock()
    # User 999 tries to cancel booking owned by user 123 — sheets returns empty list
    sheets.load_all_bookings_for_client = AsyncMock(return_value=[])

    calendar = MagicMock()
    bot = MagicMock()

    query = MagicMock()
    query.from_user = MagicMock(id=999)
    query.message = MagicMock(spec=Message)
    query.answer = AsyncMock()

    callback_data = BookingActionCB(booking_id="bk-1", action="cancel")
    await on_cancel_booking(query, callback_data, bot, sheets, calendar)

    # Should NOT have called any cancellation side effects
    assert not hasattr(sheets, "update_booking_status") or (
        not sheets.update_booking_status.called
        if hasattr(sheets.update_booking_status, "called")
        else True
    )
    query.answer.assert_awaited_once()


async def test_cancel_skips_master_dm_when_no_telegram_id(
    confirmed_booking: Booking,
) -> None:
    """Master without telegram_id → skip DM step (still cancel cleanly)."""
    master_no_tg = Master(
        id="m1",
        name="Без телеграма",
        telegram_id=None,
        calendar_id="m1@example.com",
        work_hours="10:00-19:00",
        work_days=[1, 2, 3, 4, 5],
        is_active=True,
    )
    recorder: list[str] = []

    sheets = MagicMock()
    sheets.load_all_bookings_for_client = AsyncMock(return_value=[confirmed_booking])
    sheets.load_masters = AsyncMock(return_value=[master_no_tg])
    sheets.update_booking_status = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("sheets.update")
    )

    calendar = MagicMock()
    calendar.delete_event = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("calendar.delete")
    )

    bot = MagicMock()
    bot.send_message = AsyncMock()  # should NOT be called

    query = MagicMock()
    query.from_user = MagicMock(id=123)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    with patch(
        "bot.handlers.my_bookings.cancel_reminders",
        new=AsyncMock(side_effect=lambda *a, **kw: recorder.append("scheduler.cancel")),
    ):
        await on_cancel_booking(
            query, BookingActionCB(booking_id="bk-1", action="cancel"), bot, sheets, calendar
        )

    assert recorder == ["scheduler.cancel", "calendar.delete", "sheets.update"]
    bot.send_message.assert_not_called()


async def test_cancel_treats_calendar_404_as_success(
    confirmed_booking: Booking, master_with_telegram: Master
) -> None:
    """Already-deleted event (404/not-found) should not block status flip."""
    recorder: list[str] = []

    sheets = MagicMock()
    sheets.load_all_bookings_for_client = AsyncMock(return_value=[confirmed_booking])
    sheets.load_masters = AsyncMock(return_value=[master_with_telegram])
    sheets.update_booking_status = AsyncMock(
        side_effect=lambda *a, **kw: recorder.append("sheets.update")
    )

    calendar = MagicMock()
    # Calendar delete raises with 404 in the message — handler treats as gone
    calendar.delete_event = AsyncMock(side_effect=Exception("HTTP 404: Resource has been deleted"))

    bot = MagicMock()
    bot.send_message = AsyncMock()

    query = MagicMock()
    query.from_user = MagicMock(id=123)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    with patch(
        "bot.handlers.my_bookings.cancel_reminders",
        new=AsyncMock(),
    ):
        await on_cancel_booking(
            query, BookingActionCB(booking_id="bk-1", action="cancel"), bot, sheets, calendar
        )

    # The Sheet flip still happened despite the calendar 404
    assert recorder == ["sheets.update"]
