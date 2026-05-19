"""Cache TTL behavior tests for CalendarService.query_busy_intervals.

Bypasses CalendarService.__init__ (which reads credentials.json) by using
`__new__` + manual attribute setup. Mocks `time.monotonic` to fast-forward
through the 60-second TTL window and asserts API call counts.
"""

from datetime import date
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from bot.services.calendar import CalendarService


@pytest.fixture
def cs(monkeypatch: pytest.MonkeyPatch) -> CalendarService:
    """CalendarService instance with init bypassed and mocked service."""
    cs = CalendarService.__new__(CalendarService)
    cs._service = MagicMock()
    cs._busy_cache = {}
    cs._local_tz = ZoneInfo("Europe/Kyiv")
    # Default empty-busy response; tests override on the chained execute mock.
    cs._service.freebusy().query().execute.return_value = {"calendars": {"cal-1": {"busy": []}}}
    # Reset the call_count that was already incremented by the chain setup above.
    cs._service.reset_mock()
    return cs


def _fake_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch bot.services.calendar.time.monotonic to a controllable clock."""
    holder = [100.0]
    monkeypatch.setattr("bot.services.calendar.time.monotonic", lambda: holder[0])
    return holder


async def test_cache_hit_within_ttl(cs: CalendarService, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _fake_clock(monkeypatch)
    execute = cs._service.freebusy.return_value.query.return_value.execute
    execute.return_value = {"calendars": {"cal-1": {"busy": []}}}

    # First call — API hit
    clock[0] = 100.0
    await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    assert execute.call_count == 1

    # Second call within TTL (59 sec later) — cache hit, no new API call
    clock[0] = 159.0
    await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    assert execute.call_count == 1


async def test_cache_miss_after_ttl(cs: CalendarService, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _fake_clock(monkeypatch)
    execute = cs._service.freebusy.return_value.query.return_value.execute
    execute.return_value = {"calendars": {"cal-1": {"busy": []}}}

    clock[0] = 100.0
    await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    assert execute.call_count == 1

    # 61 seconds later — past TTL, cache miss, new API call
    clock[0] = 161.0
    await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    assert execute.call_count == 2


async def test_cache_keys_distinct_per_calendar_and_date(
    cs: CalendarService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different calendar_id or different date should NOT share cache entries."""
    clock = _fake_clock(monkeypatch)
    clock[0] = 100.0
    execute = cs._service.freebusy.return_value.query.return_value.execute
    execute.return_value = {
        "calendars": {
            "cal-1": {"busy": []},
            "cal-2": {"busy": []},
        }
    }

    await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    await cs.query_busy_intervals("cal-2", date(2026, 5, 20))  # different cal_id
    await cs.query_busy_intervals("cal-1", date(2026, 5, 21))  # different date

    # Three distinct keys → three API calls within TTL window
    assert execute.call_count == 3


async def test_response_parsing_normalizes_to_naive_kyiv(
    cs: CalendarService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UTC RFC3339 (Z suffix) → naive Europe/Kyiv datetimes."""
    clock = _fake_clock(monkeypatch)
    clock[0] = 100.0
    execute = cs._service.freebusy.return_value.query.return_value.execute
    # 12:00–13:00 UTC = 15:00–16:00 Kyiv (summer, UTC+3)
    execute.return_value = {
        "calendars": {
            "cal-1": {"busy": [{"start": "2026-05-20T12:00:00Z", "end": "2026-05-20T13:00:00Z"}]}
        }
    }

    intervals = await cs.query_busy_intervals("cal-1", date(2026, 5, 20))
    assert len(intervals) == 1
    start, end = intervals[0]
    assert start.tzinfo is None  # naive
    assert end.tzinfo is None
    assert start.hour == 15  # 12 UTC → 15 Kyiv (DST)
    assert end.hour == 16
