"""Slot availability — pure function, no I/O.

Algorithm per project_specs.md §9.5. Caller pre-loads bookings, blackouts,
and Google Calendar busy intervals; this function decides which candidate
slots remain free.

Convention: all datetime inputs are assumed to be in the same timezone
(tz-naive locals OR all tz-aware in the same zone). Mixing tz-naive
and tz-aware in `confirmed_bookings` and `calendar_busy_intervals`
will raise `TypeError` from the standard comparison operators.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from bot.models import Blackout, Booking, Master, Service


def calculate_available_slots(
    master: Master,
    d: date,
    service: Service,
    confirmed_bookings: Sequence[Booking],
    blackouts: Sequence[Blackout],
    calendar_busy_intervals: Sequence[tuple[datetime, datetime]] = (),
) -> list[datetime]:
    if d.isoweekday() not in master.work_days:
        return []

    for bo in blackouts:
        if bo.date != d:
            continue
        if bo.master_id in ("*", master.id):
            return []

    sh, sm, eh, em = master.parse_work_hours()
    day_start = datetime.combine(d, datetime.min.time()).replace(hour=sh, minute=sm)
    day_end = datetime.combine(d, datetime.min.time()).replace(hour=eh, minute=em)
    step = timedelta(minutes=service.duration_min)

    candidates: list[datetime] = []
    cur = day_start
    while cur + step <= day_end:
        candidates.append(cur)
        cur += step

    busy: list[tuple[datetime, datetime]] = []
    for b in confirmed_bookings:
        if b.status != "confirmed":
            continue
        busy.append((b.datetime_start, b.datetime_end))
    for cs, ce in calendar_busy_intervals:
        busy.append((cs, ce))

    available: list[datetime] = []
    for slot in candidates:
        slot_end = slot + step
        if any(slot_end > bs and slot < be for bs, be in busy):
            continue
        available.append(slot)
    return available
