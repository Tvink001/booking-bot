"""Module-scope APScheduler callable for daily VIP sweep. Body in Prompt 8.

Same module-scope rule as `reminders.py` — see that file for the reason.
"""

import logging

logger = logging.getLogger(__name__)


async def check_vip_promos() -> None:
    # Body in Prompt 8 (§16): scan clients with ≥5 completed bookings,
    # send one-time VIP DM, mark notified.
    logger.info("TODO Prompt 8: check_vip_promos daily cron")
