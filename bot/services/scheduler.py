"""APScheduler 4 wrapper.

Module-level singleton `scheduler` created at import time (no I/O until
`__aenter__`). Lifecycle (enter context + start worker) is owned by
`bot/main.py` `on_startup`; teardown by `on_shutdown`.

DO NOT pass `add_schedule` a lambda, closure, or nested def — the CBOR
serializer stores the dotted-path reference, and non-importable callables
silently lose their jobs on restart. See `bot/handlers/reminders.py` and
project_specs.md §14.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.serializers.pickle import PickleSerializer
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import create_async_engine

from bot.config import settings
from bot.handlers.reminders import send_reminder

logger = logging.getLogger(__name__)

# Absolute POSIX path for clarity and to avoid Windows backslash quirks
# in the SQLAlchemy URL parser.
_DB_URL = f"sqlite+aiosqlite:///{settings.scheduler_db_path.resolve().as_posix()}"

_engine = create_async_engine(_DB_URL)
_data_store = SQLAlchemyDataStore(_engine, serializer=PickleSerializer())
scheduler: AsyncScheduler = AsyncScheduler(_data_store)


def _reminder_id(booking_id: str, kind: int) -> str:
    return f"reminder_{kind}h_{booking_id}"


async def schedule_reminder(booking_id: str, fire_at: datetime, kind: int) -> None:
    """Schedule a one-shot reminder; idempotent via `ConflictPolicy.replace`."""
    sid = _reminder_id(booking_id, kind)
    await scheduler.add_schedule(
        send_reminder,
        DateTrigger(run_time=fire_at),
        id=sid,
        args=(booking_id, kind),
        conflict_policy=ConflictPolicy.replace,
    )
    logger.info("Scheduled %s at %s", sid, fire_at.isoformat())


async def cancel_reminders(booking_id: str) -> None:
    """Cancel both 24h and 1h reminders for a booking. Silent on already-gone.

    Logs INFO only when a real schedule was present and removed. Logs DEBUG
    when the schedule didn't exist (no-op) — APScheduler 4 alpha's
    `remove_schedule` no-ops silently on missing ids, so we probe with
    `get_schedule` first to distinguish the two cases.
    """
    for kind in (24, 1):
        sid = _reminder_id(booking_id, kind)
        existed = False
        try:
            await scheduler.get_schedule(sid)
            existed = True
        except Exception:  # noqa: BLE001  --  alpha doesn't export lookup error
            pass
        try:
            await scheduler.remove_schedule(sid)
        except Exception as exc:  # noqa: BLE001  --  benign: already-gone
            logger.debug("Schedule %s remove failed: %s", sid, exc)
            continue
        if existed:
            logger.info("Cancelled schedule %s", sid)
        else:
            logger.debug("Schedule %s not present (no-op)", sid)


async def schedule_daily_job(
    job_id: str,
    callback: Callable[..., Awaitable[Any]],
    hour: int,
    minute: int,
) -> None:
    """Register a cron-driven daily job. Idempotent — safe on every startup."""
    await scheduler.add_schedule(
        callback,
        CronTrigger(hour=hour, minute=minute, timezone=settings.scheduler_timezone),
        id=job_id,
        conflict_policy=ConflictPolicy.replace,
    )
    logger.info(
        "Scheduled daily %s at %02d:%02d %s",
        job_id,
        hour,
        minute,
        settings.scheduler_timezone,
    )
