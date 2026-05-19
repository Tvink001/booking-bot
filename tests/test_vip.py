"""Pure-logic tests for `bot.handlers.vip.select_vip_candidates`.

No I/O mocking — the helper is intentionally pure (no Bot, no Sheets).
Covers the four cases enumerated in project_specs.md §16.8.
"""

from datetime import datetime, timedelta

from bot.handlers.vip import select_vip_candidates
from bot.models import Booking


def _booking(tid: int, status: str, days_offset: int = 0) -> Booking:
    """Build a minimal Booking for VIP candidate testing.

    Only `client_telegram_id`, `status`, and `datetime_start` are
    semantically meaningful for these tests; the other fields are
    filled with placeholder values.
    """
    start = datetime.now() + timedelta(days=days_offset)
    return Booking(
        id=f"bk-{tid}-{status}-{days_offset}",
        client_telegram_id=tid,
        client_name=f"Client{tid}",
        client_phone="+380501234567",
        service_id="haircut-30",
        master_id="m1",
        datetime_start=start,
        datetime_end=start + timedelta(minutes=30),
        status=status,
        created_at=datetime.now(),
    )


def test_4_completed_with_upcoming_is_not_candidate() -> None:
    """Below the 5-visit threshold → no DM."""
    tid = 100
    completed = [_booking(tid, "completed", days_offset=-30 - i) for i in range(4)]
    upcoming = [_booking(tid, "confirmed", days_offset=3)]
    assert select_vip_candidates(completed, upcoming, already_sent=set()) == []


def test_5_completed_plus_upcoming_fresh_is_candidate() -> None:
    """At/above threshold + has upcoming + not previously sent → candidate."""
    tid = 200
    completed = [_booking(tid, "completed", days_offset=-30 - i) for i in range(5)]
    upcoming = [_booking(tid, "confirmed", days_offset=2)]
    assert select_vip_candidates(completed, upcoming, already_sent=set()) == [tid]


def test_5_completed_plus_upcoming_but_already_sent_is_skipped() -> None:
    """Idempotency: prior DM in `_vip_sent` → never re-fired."""
    tid = 300
    completed = [_booking(tid, "completed", days_offset=-30 - i) for i in range(5)]
    upcoming = [_booking(tid, "confirmed", days_offset=2)]
    assert select_vip_candidates(completed, upcoming, already_sent={tid}) == []


def test_5_completed_but_no_upcoming_is_skipped() -> None:
    """Inactive client (no upcoming) → no DM, even though they're VIP-eligible."""
    tid = 400
    completed = [_booking(tid, "completed", days_offset=-30 - i) for i in range(5)]
    upcoming: list[Booking] = []
    assert select_vip_candidates(completed, upcoming, already_sent=set()) == []


def test_multiple_clients_returned_sorted() -> None:
    """Stable ordering: candidates returned sorted by telegram ID."""
    completed = (
        [_booking(300, "completed", days_offset=-30 - i) for i in range(5)]
        + [_booking(100, "completed", days_offset=-30 - i) for i in range(5)]
        + [_booking(200, "completed", days_offset=-30 - i) for i in range(5)]
    )
    upcoming = [
        _booking(100, "confirmed", days_offset=1),
        _booking(200, "confirmed", days_offset=2),
        _booking(300, "confirmed", days_offset=3),
    ]
    assert select_vip_candidates(completed, upcoming, already_sent=set()) == [100, 200, 300]
