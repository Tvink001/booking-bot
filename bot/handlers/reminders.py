"""Module-scope APScheduler callable for booking reminders.

Two HARD constraints (CLAUDE.md + project_specs.md §14):

1. **Module-scope callable.** APScheduler 4's `SQLAlchemyDataStore` +
   `CBORSerializer` stores `send_reminder` as a dotted-path reference.
   A lambda / closure / nested def cannot be re-resolved after restart
   and the job silently disappears. Keep this function at module scope.

2. **Write-after-success idempotency.** Send the DM first; only after
   Telegram returns 200, flip the `reminder_X_sent` flag in Sheets.
   If the DM fails → flag stays unset, next attempt retries. If the
   flag flips but DM is somehow re-fired (e.g. duplicate restart),
   the in-handler `already_sent` guard skips. Belt + suspenders.

**Bot injection.** `args=(booking_id, hours_offset)` must be CBOR-
serializable; `Bot` is not (open HTTP session, etc.). Instead, we
hold the Bot + SheetsService as module-level globals, populated by
`set_runtime(bot, sheets)` from `bot/main.py` `on_startup` BEFORE
`scheduler.start_in_background()` — so the first fire after restart
sees both refs set.
"""

import logging

from aiogram import Bot

from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)


MSG_REMINDER_24H_TEMPLATE = (
    "⏰ Напоминание: завтра в {time_str} у вас запись на «{service_name}» "
    "к мастеру {master_name}."
)
MSG_REMINDER_1H_TEMPLATE = "🔔 Через час — запись «{service_name}» у мастера {master_name}."

# Module-level runtime refs, set once at startup. See module docstring.
_bot: Bot | None = None
_sheets: SheetsService | None = None


def set_runtime(bot: Bot, sheets: SheetsService) -> None:
    """Inject runtime singletons into this module.

    Must be called from `bot/main.py:on_startup` BEFORE
    `scheduler.start_in_background()` — otherwise an immediately-due
    job could fire with `_bot` still None.
    """
    global _bot, _sheets
    _bot = bot
    _sheets = sheets


async def send_reminder(booking_id: str, hours_offset: int) -> None:
    """APScheduler-fired callable. Sends a reminder DM to the client.

    Order:
    1. Load booking fresh
    2. Skip if status != 'confirmed' (cancellation race)
    3. Skip if the matching `reminder_X_sent` flag is already truthy
    4. Send DM (may raise)
    5. Flip the flag — only AFTER step 4 succeeds

    If step 4 raises, the exception propagates to APScheduler's error
    handler (logged in stdout). The flag stays unset → next scheduled
    fire retries.
    """
    if _bot is None or _sheets is None:
        logger.error(
            "send_reminder(%s, %d) fired before set_runtime — skipping",
            booking_id,
            hours_offset,
        )
        return

    booking = await _sheets.load_booking_by_id(booking_id)
    if booking is None:
        logger.warning(
            "Reminder %dh fired for missing booking %s — skip",
            hours_offset,
            booking_id,
        )
        return

    if booking.status != "confirmed":
        logger.info(
            "Reminder %dh: booking %s status=%s — skip",
            hours_offset,
            booking_id,
            booking.status,
        )
        return

    already_sent = (hours_offset == 24 and booking.reminder_24_sent) or (
        hours_offset == 1 and booking.reminder_1_sent
    )
    if already_sent:
        logger.info(
            "Reminder %dh: booking %s flag already set — skip",
            hours_offset,
            booking_id,
        )
        return

    masters = await _sheets.load_masters()
    services = await _sheets.load_services()
    master = next((m for m in masters if m.id == booking.master_id), None)
    service = next((s for s in services if s.id == booking.service_id), None)
    master_name = master.name if master else booking.master_id
    service_name = service.name if service else booking.service_id

    template = MSG_REMINDER_24H_TEMPLATE if hours_offset == 24 else MSG_REMINDER_1H_TEMPLATE
    text = template.format(
        time_str=booking.datetime_start.strftime("%H:%M"),
        service_name=service_name,
        master_name=master_name,
    )

    # Step 4: Send DM. If this raises, step 5 is skipped — flag stays unset.
    await _bot.send_message(chat_id=booking.client_telegram_id, text=text)

    # Step 5: Flip flag — only after step 4 succeeds.
    await _sheets.set_reminder_sent_flag(booking_id, hours_offset)
    logger.info("Reminder %dh sent for booking %s", hours_offset, booking_id)
