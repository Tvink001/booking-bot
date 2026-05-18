"""Module-scope APScheduler callable for reminders. Body filled in Prompt 6.

CRITICAL (CLAUDE.md constraint, project_specs.md §14):
APScheduler 4's `SQLAlchemyDataStore` + `CBORSerializer` serializes the
callable reference by its full dotted path. A lambda, closure, or
function defined inside another function CANNOT be re-resolved after a
restart — the scheduler silently drops the job. This function must stay
at module scope.
"""

import logging

logger = logging.getLogger(__name__)


async def send_reminder(booking_id: str, hours_before: int) -> None:
    # Body in Prompt 6: re-read booking, idempotency guard, DM, set flag.
    logger.info(
        "TODO Prompt 6: send_reminder booking_id=%s hours_before=%d",
        booking_id,
        hours_before,
    )
