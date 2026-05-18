"""Domain models for booking-bot.

Pydantic v2 BaseModel for type safety. Each model that maps to a Sheet tab
provides `from_row(dict)` for reading from `worksheet.get_all_records()`.
Booking additionally provides `to_row()` for writing via `append_row()` —
the list order must match the column order in project_specs.md §7.3.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


def _parse_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _csv_strs(v: Any) -> list[str]:
    s = str(v or "").strip()
    return [x.strip() for x in s.split(",") if x.strip()]


def _csv_ints(v: Any) -> list[int]:
    """Parse CSV ints, with fallback for Google Sheets locale quirk.

    Google Sheets with comma-as-thousands-separator locale interprets a
    text-typed cell `"1,2,3,4,5,6"` as the number 123456 — gspread then
    returns int, not str. If we see an int whose digits are all in [1,7],
    treat it as concatenated weekdays. Otherwise fall through to the
    normal CSV-string parse.
    """
    if isinstance(v, int) and not isinstance(v, bool):
        digits = str(v)
        if digits.isdigit() and all(c in "1234567" for c in digits):
            return [int(c) for c in digits]
        return []
    return [int(x) for x in _csv_strs(v)]


class Service(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    duration_min: int
    price: int
    master_ids: list[str]
    is_active: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Service":
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            duration_min=int(row["duration_min"]),
            price=int(row.get("price") or 0),
            master_ids=_csv_strs(row.get("master_ids")),
            is_active=_parse_bool(row.get("is_active")),
        )


class Master(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    telegram_id: int | None
    calendar_id: str
    work_hours: str  # "HH:MM-HH:MM"
    work_days: list[int]  # ISO weekday (Mon=1..Sun=7)
    is_active: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Master":
        tg_raw = row.get("telegram_id")
        tg: int | None = None
        if tg_raw is not None and tg_raw != "" and tg_raw != 0:
            tg = int(tg_raw)
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            telegram_id=tg,
            calendar_id=str(row["calendar_id"]),
            work_hours=str(row.get("work_hours") or "10:00-19:00"),
            work_days=_csv_ints(row.get("work_days")),
            is_active=_parse_bool(row.get("is_active")),
        )

    def parse_work_hours(self) -> tuple[int, int, int, int]:
        start, end = self.work_hours.split("-")
        sh, sm = start.strip().split(":")
        eh, em = end.strip().split(":")
        return int(sh), int(sm), int(eh), int(em)


class Blackout(BaseModel):
    model_config = ConfigDict(frozen=True)

    master_id: str  # or "*" for all masters
    date: date
    reason: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Blackout":
        d_raw = row["date"]
        d = d_raw if isinstance(d_raw, date) else date.fromisoformat(str(d_raw))
        return cls(
            master_id=str(row["master_id"]),
            date=d,
            reason=str(row.get("reason") or ""),
        )


class Booking(BaseModel):
    id: str
    client_telegram_id: int
    client_name: str
    client_phone: str
    service_id: str
    master_id: str
    datetime_start: datetime
    datetime_end: datetime
    status: str  # confirmed | cancelled | completed | no_show
    reminder_24_sent: bool = False
    reminder_1_sent: bool = False
    created_at: datetime
    cancelled_at: datetime | None = None
    calendar_event_id: str | None = None
    visit_count_snapshot: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Booking":
        def _opt_dt(v: Any) -> datetime | None:
            if not v:
                return None
            return datetime.fromisoformat(str(v))

        return cls(
            id=str(row["id"]),
            client_telegram_id=int(row["client_telegram_id"]),
            client_name=str(row.get("client_name") or ""),
            client_phone=str(row.get("client_phone") or ""),
            service_id=str(row["service_id"]),
            master_id=str(row["master_id"]),
            datetime_start=datetime.fromisoformat(str(row["datetime_start"])),
            datetime_end=datetime.fromisoformat(str(row["datetime_end"])),
            status=str(row.get("status") or "confirmed"),
            reminder_24_sent=_parse_bool(row.get("reminder_24_sent")),
            reminder_1_sent=_parse_bool(row.get("reminder_1_sent")),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            cancelled_at=_opt_dt(row.get("cancelled_at")),
            calendar_event_id=(str(row.get("calendar_event_id") or "") or None),
            visit_count_snapshot=int(row.get("visit_count_snapshot") or 0),
        )

    def to_row(self) -> list[Any]:
        # Order MUST match §7.3 columns A..O.
        return [
            self.id,
            self.client_telegram_id,
            self.client_name,
            self.client_phone,
            self.service_id,
            self.master_id,
            self.datetime_start.isoformat(),
            self.datetime_end.isoformat(),
            self.status,
            "TRUE" if self.reminder_24_sent else "FALSE",
            "TRUE" if self.reminder_1_sent else "FALSE",
            self.created_at.isoformat(),
            self.cancelled_at.isoformat() if self.cancelled_at else "",
            self.calendar_event_id or "",
            self.visit_count_snapshot,
        ]
