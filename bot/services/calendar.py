"""Google Calendar v3 wrapper. Sync API wrapped via `asyncio.to_thread`.

Provides create/delete event and freebusy query for WOW 1 (slot exclusion
based on manually-blocked Calendar time). Includes a per-(calendar_id, date)
in-memory cache with 60s TTL — see project_specs.md §15.

Constructor opens the discovery-built service; `cache_discovery=False`
suppresses the file-cache warning on systems without a writable cache.
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from bot.config import settings
from bot.models import Booking

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_CACHE_TTL_SECONDS = 60.0


class CalendarService:
    """Thin async wrapper over google-api-python-client Calendar v3."""

    def __init__(self) -> None:
        creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            str(settings.google_service_account_path), scopes=_SCOPES
        )
        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        # Cache: (calendar_id, iso_date) -> (monotonic_set_at, intervals)
        self._busy_cache: dict[tuple[str, str], tuple[float, list[tuple[datetime, datetime]]]] = {}
        self._local_tz = ZoneInfo(settings.google_calendar_default_tz)

    async def create_event(self, master_calendar_id: str, booking: Booking) -> str:
        body = {
            "summary": f"{booking.client_name} — {booking.service_id}",
            "start": {
                "dateTime": booking.datetime_start.isoformat(),
                "timeZone": settings.google_calendar_default_tz,
            },
            "end": {
                "dateTime": booking.datetime_end.isoformat(),
                "timeZone": settings.google_calendar_default_tz,
            },
            "description": (f"Client phone: {booking.client_phone}\n" f"Booking ID: {booking.id}"),
        }

        def _insert() -> Any:
            return self._service.events().insert(calendarId=master_calendar_id, body=body).execute()

        event = await asyncio.to_thread(_insert)
        # Invalidate cache for that day so the next freebusy reflects this event.
        self._busy_cache.pop(
            (master_calendar_id, booking.datetime_start.date().isoformat()),
            None,
        )
        return str(event["id"])

    async def delete_event(self, master_calendar_id: str, event_id: str) -> None:
        def _delete() -> None:
            self._service.events().delete(calendarId=master_calendar_id, eventId=event_id).execute()

        await asyncio.to_thread(_delete)

    async def query_busy_intervals(
        self, master_calendar_id: str, d: date
    ) -> list[tuple[datetime, datetime]]:
        """Return busy intervals on `d` for `master_calendar_id`.

        Output intervals are tz-naive in the default local timezone
        (`settings.google_calendar_default_tz`), matching the convention
        used elsewhere for booking datetimes.
        """
        key = (master_calendar_id, d.isoformat())
        now_mono = time.monotonic()
        cached = self._busy_cache.get(key)
        if cached and now_mono - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        # Day bounds in Europe/Kyiv (not UTC) — otherwise events at the
        # start of the Kyiv day (00:00–03:00 in summer) fall outside the
        # query window for that date.
        day_start_local = datetime.combine(d, datetime.min.time()).replace(tzinfo=self._local_tz)
        day_end_local = day_start_local + timedelta(days=1)

        def _query() -> Any:
            return (
                self._service.freebusy()
                .query(
                    body={
                        "timeMin": day_start_local.isoformat(),
                        "timeMax": day_end_local.isoformat(),
                        "items": [{"id": master_calendar_id}],
                        "timeZone": settings.google_calendar_default_tz,
                    }
                )
                .execute()
            )

        result = await asyncio.to_thread(_query)
        busy_raw = result.get("calendars", {}).get(master_calendar_id, {}).get("busy", [])
        intervals: list[tuple[datetime, datetime]] = []
        for b in busy_raw:
            start_utc = datetime.fromisoformat(str(b["start"]).replace("Z", "+00:00"))
            end_utc = datetime.fromisoformat(str(b["end"]).replace("Z", "+00:00"))
            start_local = start_utc.astimezone(self._local_tz).replace(tzinfo=None)
            end_local = end_utc.astimezone(self._local_tz).replace(tzinfo=None)
            intervals.append((start_local, end_local))

        self._busy_cache[key] = (now_mono, intervals)
        return intervals
