"""gspread wrapper for the five tabs.

All public methods are async — sync gspread calls are wrapped via
`asyncio.to_thread` (CLAUDE.md constraint). Worksheets opened once in
the constructor and reused; methods take a few hundred ms cold start
on first request after a long idle.

This module defines the `SheetsService` class but does NOT instantiate
it at module level — construction is the entry point's responsibility
(typically in `bot/main.py` startup). This keeps tests of pure modules
(`slots.py`, `phone.py`) from needing credentials to import.
"""

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Any

import gspread
from gspread.utils import ValueInputOption

from bot.config import settings
from bot.models import Blackout, Booking, Master, Service

logger = logging.getLogger(__name__)

_REDACT_RE = re.compile(r"(token|key|password|secret|credential)", re.IGNORECASE)


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: ("[REDACTED]" if _REDACT_RE.search(k) else v) for k, v in payload.items()}


def _cell_value(v: Any) -> Any:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if v is None:
        return ""
    return v


class SheetsService:
    """Thin async wrapper over gspread. One instance per process."""

    def __init__(self) -> None:
        self._gc = gspread.service_account(filename=str(settings.google_service_account_path))
        self._sh = self._gc.open_by_key(settings.google_sheet_id)
        self._ws_services = self._sh.worksheet("services")
        self._ws_masters = self._sh.worksheet("masters")
        self._ws_bookings = self._sh.worksheet("bookings")
        self._ws_blackouts = self._sh.worksheet("blackouts")
        self._ws_errors = self._sh.worksheet("_errors")

    # ---------- reads ----------

    async def load_services(self) -> list[Service]:
        rows = await asyncio.to_thread(self._ws_services.get_all_records, head=1)
        return [Service.from_row(r) for r in rows if r.get("id")]

    async def load_masters(self) -> list[Master]:
        rows = await asyncio.to_thread(self._ws_masters.get_all_records, head=1)
        return [Master.from_row(r) for r in rows if r.get("id")]

    async def load_blackouts_for_date(self, d: date) -> list[Blackout]:
        rows = await asyncio.to_thread(self._ws_blackouts.get_all_records, head=1)
        target_iso = d.isoformat()
        out: list[Blackout] = []
        for r in rows:
            if not r.get("master_id"):
                continue
            raw = r.get("date")
            if isinstance(raw, date) and not isinstance(raw, datetime):
                if raw == d:
                    out.append(Blackout.from_row(r))
            elif str(raw) == target_iso:
                out.append(Blackout.from_row(r))
        return out

    async def load_bookings_for_master_date(self, master_id: str, d: date) -> list[Booking]:
        rows = await asyncio.to_thread(self._ws_bookings.get_all_records, head=1)
        out: list[Booking] = []
        for r in rows:
            if not r.get("id"):
                continue
            if str(r.get("master_id")) != master_id:
                continue
            try:
                dt = datetime.fromisoformat(str(r["datetime_start"]))
            except (KeyError, ValueError):
                continue
            if dt.date() != d:
                continue
            out.append(Booking.from_row(r))
        return out

    async def load_all_bookings_for_client(self, client_telegram_id: int) -> list[Booking]:
        rows = await asyncio.to_thread(self._ws_bookings.get_all_records, head=1)
        out: list[Booking] = []
        for r in rows:
            if not r.get("id"):
                continue
            try:
                if int(r.get("client_telegram_id") or 0) != client_telegram_id:
                    continue
            except (TypeError, ValueError):
                continue
            out.append(Booking.from_row(r))
        return out

    # ---------- writes ----------

    async def append_booking(self, booking: Booking) -> None:
        await asyncio.to_thread(
            self._ws_bookings.append_row,
            booking.to_row(),
            value_input_option=ValueInputOption.user_entered,
        )

    async def update_booking_status(self, booking_id: str, status: str, **fields: Any) -> None:
        """Flip status + optional extra columns (e.g. cancelled_at, calendar_event_id)."""
        row_idx = await self._find_booking_row(booking_id)
        if row_idx is None:
            raise KeyError(f"Booking {booking_id} not found")
        header = await asyncio.to_thread(self._ws_bookings.row_values, 1)
        idx_map = {name: i + 1 for i, name in enumerate(header)}

        updates: list[dict[str, Any]] = [
            {
                "range": gspread.utils.rowcol_to_a1(row_idx, idx_map["status"]),
                "values": [[status]],
            }
        ]
        for key, val in fields.items():
            if key not in idx_map:
                logger.warning("update_booking_status: unknown field %s", key)
                continue
            updates.append(
                {
                    "range": gspread.utils.rowcol_to_a1(row_idx, idx_map[key]),
                    "values": [[_cell_value(val)]],
                }
            )

        await asyncio.to_thread(self._ws_bookings.batch_update, updates)

    async def set_reminder_sent_flag(self, booking_id: str, kind: int) -> None:
        if kind not in (1, 24):
            raise ValueError(f"kind must be 1 or 24, got {kind}")
        row_idx = await self._find_booking_row(booking_id)
        if row_idx is None:
            raise KeyError(f"Booking {booking_id} not found")
        header = await asyncio.to_thread(self._ws_bookings.row_values, 1)
        col_name = f"reminder_{kind}_sent"
        col_idx = header.index(col_name) + 1
        cell_a1 = gspread.utils.rowcol_to_a1(row_idx, col_idx)
        await asyncio.to_thread(
            self._ws_bookings.update,
            [["TRUE"]],
            cell_a1,
            value_input_option=ValueInputOption.user_entered,
        )

    async def log_error(
        self,
        handler: str,
        user_id: int,
        error_text: str,
        payload: dict[str, Any],
    ) -> None:
        row: list[str | int | float] = [
            datetime.now().isoformat(),
            handler,
            user_id,
            error_text[:500],
            json.dumps(_sanitize_payload(payload), default=str, ensure_ascii=False),
        ]
        await asyncio.to_thread(self._ws_errors.append_row, row)

    # ---------- internal ----------

    async def _find_booking_row(self, booking_id: str) -> int | None:
        values = await asyncio.to_thread(self._ws_bookings.get_all_values)
        if not values:
            return None
        header = values[0]
        if "id" not in header:
            return None
        col_idx = header.index("id")
        for i, row in enumerate(values[1:], start=2):
            if col_idx < len(row) and row[col_idx] == booking_id:
                return i
        return None
