"""Module-scope APScheduler callable for the daily VIP sweep (WOW 2).

See `project_specs.md` §16 for the full spec. Two HARD constraints (CLAUDE.md
+ reminders.py — same rules):

1. **Module-scope callable.** APScheduler's data store serializes
   `check_vip_promos` by dotted path; a lambda / closure / nested def
   cannot be re-resolved after restart.

2. **Write-after-success idempotency.** Send DM first; only on Telegram
   success append the row to `_vip_sent`. A failed send retries on the
   next daily run — Telegram blocks / network blips self-heal.

Candidate selection is extracted into a pure helper
(`select_vip_candidates`) so it's unit-testable without mocking I/O.
"""

import asyncio
import logging
from collections import Counter
from datetime import date, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.models import Booking
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)


VIP_MESSAGE_TEMPLATE = (
    "⭐ {name}, вы наш VIP-клиент после 5 визитов! " "Промокод SUPERVIP на ваш следующий визит."
)

VIP_VISIT_THRESHOLD = 5
VIP_UPCOMING_WINDOW_DAYS = 7
VIP_SEND_DELAY_SECONDS = 0.05  # 30 msg/sec Telegram global cap → 20/sec headroom.

# Module-level runtime refs, set once at startup. See module docstring of
# `bot/handlers/reminders.py` for the rationale (Bot is not CBOR/Pickle-able).
_bot: Bot | None = None
_sheets: SheetsService | None = None


def set_runtime(bot: Bot, sheets: SheetsService) -> None:
    """Inject runtime singletons into this module.

    Must be called from `bot/main.py:on_startup` BEFORE
    `scheduler.start_in_background()` — same ordering rule as
    `bot.handlers.reminders.set_runtime`.
    """
    global _bot, _sheets
    _bot = bot
    _sheets = sheets


def select_vip_candidates(
    completed: list[Booking],
    upcoming: list[Booking],
    already_sent: set[int],
) -> list[int]:
    """Return sorted telegram IDs that qualify for a VIP DM right now.

    Pure (no I/O). See `project_specs.md` §16.3 for the algorithm and
    `tests/test_vip.py` for the case matrix.
    """
    visits: Counter[int] = Counter(b.client_telegram_id for b in completed)
    upcoming_ids = {b.client_telegram_id for b in upcoming}
    return sorted(
        tid
        for tid in upcoming_ids
        if visits[tid] >= VIP_VISIT_THRESHOLD and tid not in already_sent
    )


def _client_name_for(completed: list[Booking], tid: int) -> str:
    """Pick the client_name from the most recent completed booking.

    Falls back to an empty-string-friendly placeholder if no name is
    available (shouldn't happen for a real candidate, but defensive).
    """
    matches = [b for b in completed if b.client_telegram_id == tid]
    if not matches:
        return "клиент"
    latest = max(matches, key=lambda b: b.datetime_start)
    return latest.client_name or "клиент"


async def check_vip_promos() -> None:
    """APScheduler-fired daily sweep. See module docstring + §16.

    Steps:
    1. Load all bookings; partition into `completed` and `upcoming`
       (status='confirmed' AND datetime_start in [today, today+7d]).
    2. Load `_vip_sent` set.
    3. Select candidates via the pure helper.
    4. For each: send DM → on success append to `_vip_sent` → sleep 50 ms.
    5. Log a summary line.
    """
    if _bot is None or _sheets is None:
        logger.error("check_vip_promos fired before set_runtime — skipping")
        return

    all_bookings = await _sheets.load_all_bookings()
    today = date.today()
    window_end = today + timedelta(days=VIP_UPCOMING_WINDOW_DAYS)

    completed = [b for b in all_bookings if b.status == "completed"]
    upcoming = [
        b
        for b in all_bookings
        if b.status == "confirmed" and today <= b.datetime_start.date() <= window_end
    ]
    already_sent = await _sheets.load_vip_sent()

    candidates = select_vip_candidates(completed, upcoming, already_sent)

    sent = 0
    failed = 0
    for tid in candidates:
        name = _client_name_for(completed, tid)
        text = VIP_MESSAGE_TEMPLATE.format(name=name)
        try:
            await _bot.send_message(chat_id=tid, text=text)
        except TelegramAPIError as exc:
            logger.warning("VIP DM to %s failed: %s — will retry next run", tid, exc)
            failed += 1
            continue
        await _sheets.append_vip_sent(tid)
        sent += 1
        await asyncio.sleep(VIP_SEND_DELAY_SECONDS)

    logger.info(
        "VIP check: scanned %d completed, candidates %d, sent %d, "
        "skipped %d already-sent, failed %d",
        len(completed),
        len(candidates),
        sent,
        len(already_sent),
        failed,
    )
