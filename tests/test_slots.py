"""Pure-function tests for bot.services.slots — covers spec §19 cases."""

from datetime import date, datetime, timedelta

import pytest

from bot.models import Blackout, Booking, Master, Service
from bot.services.slots import calculate_available_slots


@pytest.fixture
def master() -> Master:
    return Master(
        id="m1",
        name="Master One",
        telegram_id=None,
        calendar_id="m1@example.com",
        work_hours="10:00-13:00",
        work_days=[1, 2, 3, 4, 5],  # Mon-Fri
        is_active=True,
    )


@pytest.fixture
def service_30() -> Service:
    return Service(
        id="haircut-30",
        name="Haircut",
        duration_min=30,
        price=300,
        master_ids=[],
        is_active=True,
    )


def _booking(
    master_id: str,
    start: datetime,
    duration_min: int,
    status: str = "confirmed",
) -> Booking:
    return Booking(
        id="b",
        client_telegram_id=1,
        client_name="X",
        client_phone="+380",
        service_id="haircut-30",
        master_id=master_id,
        datetime_start=start,
        datetime_end=start + timedelta(minutes=duration_min),
        status=status,
        created_at=start,
    )


def test_outside_work_days_returns_empty(master: Master, service_30: Service) -> None:
    # 2026-05-23 is Saturday (isoweekday 6), not in master.work_days [1..5]
    d = date(2026, 5, 23)
    assert d.isoweekday() == 6
    assert calculate_available_slots(master, d, service_30, [], []) == []


def test_master_blackout_returns_empty(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)  # Wed
    bo = Blackout(master_id=master.id, date=d, reason="vacation")
    assert calculate_available_slots(master, d, service_30, [], [bo]) == []


def test_wildcard_blackout_returns_empty(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)
    bo = Blackout(master_id="*", date=d, reason="public holiday")
    assert calculate_available_slots(master, d, service_30, [], [bo]) == []


def test_normal_day_full_grid(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)  # Wed
    slots = calculate_available_slots(master, d, service_30, [], [])
    assert len(slots) == 6  # 10:00, 10:30, 11:00, 11:30, 12:00, 12:30
    assert slots[0] == datetime(2026, 5, 20, 10, 0)
    assert slots[-1] == datetime(2026, 5, 20, 12, 30)


def test_fully_booked_returns_empty(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)
    bookings = [
        _booking(master.id, datetime(2026, 5, 20, h, m), 30)
        for h, m in [(10, 0), (10, 30), (11, 0), (11, 30), (12, 0), (12, 30)]
    ]
    assert calculate_available_slots(master, d, service_30, bookings, []) == []


def test_partial_booking_excludes_overlap(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)
    bookings = [_booking(master.id, datetime(2026, 5, 20, 11, 0), 30)]
    slots = calculate_available_slots(master, d, service_30, bookings, [])
    minutes = {s.hour * 60 + s.minute for s in slots}
    assert 11 * 60 not in minutes  # 11:00 occupied
    assert 10 * 60 in minutes
    assert 10 * 60 + 30 in minutes
    assert 11 * 60 + 30 in minutes
    assert 12 * 60 in minutes
    assert 12 * 60 + 30 in minutes


def test_calendar_busy_blocks_overlapping_slots(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)
    busy = [(datetime(2026, 5, 20, 11, 0), datetime(2026, 5, 20, 12, 0))]
    slots = calculate_available_slots(master, d, service_30, [], [], busy)
    minutes = {s.hour * 60 + s.minute for s in slots}
    assert 11 * 60 not in minutes
    assert 11 * 60 + 30 not in minutes
    assert 10 * 60 in minutes
    assert 12 * 60 in minutes


def test_cancelled_bookings_do_not_occupy(master: Master, service_30: Service) -> None:
    d = date(2026, 5, 20)
    bookings = [_booking(master.id, datetime(2026, 5, 20, 11, 0), 30, status="cancelled")]
    slots = calculate_available_slots(master, d, service_30, bookings, [])
    minutes = {s.hour * 60 + s.minute for s in slots}
    assert 11 * 60 in minutes
