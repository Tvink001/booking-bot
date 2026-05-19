"""Reminder fire tests — covers idempotency, cancellation skip, DM failure.

These mock the Bot and SheetsService refs injected into bot.handlers.reminders
via `set_runtime`. The write-after-success invariant is the most important
assertion here: when the DM raises, `set_reminder_sent_flag` MUST NOT be
called and the exception must propagate to APScheduler.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers import reminders
from bot.models import Booking, Master, Service


@pytest.fixture
def confirmed_booking() -> Booking:
    start = datetime.now() + timedelta(days=1)
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
        reminder_24_sent=False,
        reminder_1_sent=False,
    )


@pytest.fixture
def master() -> Master:
    return Master(
        id="m1",
        name="Мастер",
        telegram_id=None,
        calendar_id="m@example.com",
        work_hours="10:00-19:00",
        work_days=[1, 2, 3, 4, 5],
        is_active=True,
    )


@pytest.fixture
def service() -> Service:
    return Service(
        id="haircut-30",
        name="Стрижка",
        duration_min=30,
        price=300,
        master_ids=[],
        is_active=True,
    )


@pytest.fixture
def runtime_mocks(
    monkeypatch: pytest.MonkeyPatch,
    confirmed_booking: Booking,
    master: Master,
    service: Service,
) -> tuple[MagicMock, MagicMock]:
    bot = MagicMock()
    bot.send_message = AsyncMock()

    sheets = MagicMock()
    sheets.load_booking_by_id = AsyncMock(return_value=confirmed_booking)
    sheets.load_masters = AsyncMock(return_value=[master])
    sheets.load_services = AsyncMock(return_value=[service])
    sheets.set_reminder_sent_flag = AsyncMock()

    monkeypatch.setattr(reminders, "_bot", bot)
    monkeypatch.setattr(reminders, "_sheets", sheets)
    return bot, sheets


async def test_confirmed_booking_sends_dm_and_flips_flag(
    runtime_mocks: tuple[MagicMock, MagicMock],
    confirmed_booking: Booking,
) -> None:
    bot, sheets = runtime_mocks
    await reminders.send_reminder(confirmed_booking.id, 24)

    bot.send_message.assert_awaited_once()
    call = bot.send_message.call_args
    assert call.kwargs["chat_id"] == confirmed_booking.client_telegram_id
    assert "Стрижка" in call.kwargs["text"]
    assert "Мастер" in call.kwargs["text"]

    sheets.set_reminder_sent_flag.assert_awaited_once_with(confirmed_booking.id, 24)


async def test_cancelled_booking_skips_silently(
    runtime_mocks: tuple[MagicMock, MagicMock],
    confirmed_booking: Booking,
) -> None:
    bot, sheets = runtime_mocks
    cancelled = confirmed_booking.model_copy(update={"status": "cancelled"})
    sheets.load_booking_by_id = AsyncMock(return_value=cancelled)

    await reminders.send_reminder(confirmed_booking.id, 24)

    bot.send_message.assert_not_called()
    sheets.set_reminder_sent_flag.assert_not_called()


async def test_already_sent_flag_skips(
    runtime_mocks: tuple[MagicMock, MagicMock],
    confirmed_booking: Booking,
) -> None:
    bot, sheets = runtime_mocks
    already = confirmed_booking.model_copy(update={"reminder_24_sent": True})
    sheets.load_booking_by_id = AsyncMock(return_value=already)

    await reminders.send_reminder(confirmed_booking.id, 24)

    bot.send_message.assert_not_called()
    sheets.set_reminder_sent_flag.assert_not_called()


async def test_dm_failure_does_not_flip_flag_and_propagates(
    runtime_mocks: tuple[MagicMock, MagicMock],
    confirmed_booking: Booking,
) -> None:
    bot, sheets = runtime_mocks
    bot.send_message = AsyncMock(side_effect=RuntimeError("Telegram 500"))

    with pytest.raises(RuntimeError, match="Telegram 500"):
        await reminders.send_reminder(confirmed_booking.id, 24)

    sheets.set_reminder_sent_flag.assert_not_called()


async def test_missing_booking_returns_silently(
    runtime_mocks: tuple[MagicMock, MagicMock],
) -> None:
    bot, sheets = runtime_mocks
    sheets.load_booking_by_id = AsyncMock(return_value=None)

    await reminders.send_reminder("unknown-id", 24)

    bot.send_message.assert_not_called()
    sheets.set_reminder_sent_flag.assert_not_called()


async def test_runtime_not_set_returns_early(monkeypatch: pytest.MonkeyPatch) -> None:
    """If APScheduler fires before set_runtime (shouldn't happen — see main.py
    order — but defense in depth), don't crash."""
    monkeypatch.setattr(reminders, "_bot", None)
    monkeypatch.setattr(reminders, "_sheets", None)

    # Should not raise
    await reminders.send_reminder("bk-1", 24)


async def test_1h_reminder_uses_correct_template_and_flag(
    runtime_mocks: tuple[MagicMock, MagicMock],
    confirmed_booking: Booking,
) -> None:
    """Sanity: 1h reminder hits reminder_1_sent flag, uses 1h template text."""
    bot, sheets = runtime_mocks
    await reminders.send_reminder(confirmed_booking.id, 1)

    bot.send_message.assert_awaited_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "Через час" in text

    sheets.set_reminder_sent_flag.assert_awaited_once_with(confirmed_booking.id, 1)
