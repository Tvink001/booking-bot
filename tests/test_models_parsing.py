"""Regression tests for Sheets-tolerant datetime/date parsing.

Google Sheets renders ISO datetimes through its locale's format and may
drop leading zeros / replace `T` with space. `datetime.fromisoformat`
rejects the result. The fallback regex parser must handle every shape
Sheets emits.
"""

from datetime import date, datetime

import pytest

from bot.models import _parse_date, _parse_dt


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Standard ISO (what we write)
        ("2026-05-19T02:14:08", datetime(2026, 5, 19, 2, 14, 8)),
        ("2026-05-19T02:14:08.123456", datetime(2026, 5, 19, 2, 14, 8, 123456)),
        # Sheets-munged (what we read back) — REGRESSION CASE from Prompt 5
        ("2026-05-19 2:14:08", datetime(2026, 5, 19, 2, 14, 8)),
        ("2026-05-19 2:14", datetime(2026, 5, 19, 2, 14)),
        # Already-tolerant cases (Python 3.11 fromisoformat handles these)
        ("2026-05-19 02:14:08", datetime(2026, 5, 19, 2, 14, 8)),
        ("2026-12-31 23:59:59", datetime(2026, 12, 31, 23, 59, 59)),
        # Date only
        ("2026-05-19", datetime(2026, 5, 19)),
        # With timezone offset (we drop tz, naive Europe/Kyiv convention)
        ("2026-05-19T02:14:08+03:00", datetime(2026, 5, 19, 2, 14, 8)),
        ("2026-05-19 2:14:08Z", datetime(2026, 5, 19, 2, 14, 8)),
    ],
)
def test_parse_dt_accepts(raw: str, expected: datetime) -> None:
    # For the tz-suffixed case, fromisoformat returns tz-aware; we then
    # strip with the fallback. Accept either; compare on naive parts.
    parsed = _parse_dt(raw)
    assert parsed.replace(tzinfo=None) == expected


def test_parse_dt_empty_raises() -> None:
    with pytest.raises(ValueError):
        _parse_dt("")


def test_parse_dt_garbage_raises() -> None:
    with pytest.raises(ValueError):
        _parse_dt("not a date")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-05-19", date(2026, 5, 19)),
        ("2026-5-19", date(2026, 5, 19)),  # Sheets-munged single-digit month
        ("2026-5-9", date(2026, 5, 9)),  # both single-digit
    ],
)
def test_parse_date_accepts_strings(raw: str, expected: date) -> None:
    assert _parse_date(raw) == expected


def test_parse_date_passes_through_date_object() -> None:
    d = date(2026, 5, 19)
    assert _parse_date(d) is d


def test_parse_date_extracts_from_datetime() -> None:
    dt = datetime(2026, 5, 19, 12, 0)
    assert _parse_date(dt) == date(2026, 5, 19)


def test_parse_date_garbage_raises() -> None:
    with pytest.raises(ValueError):
        _parse_date("not a date")
