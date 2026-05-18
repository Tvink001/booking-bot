"""CallbackData factories — schema-typed inline button payloads.

Use `Factory(...).pack()` when building keyboards and
`@router.callback_query(Factory.filter(F.field == value))` when routing.
Never construct callback_data via raw f-strings on user-controllable
values (CLAUDE.md constraint).

Prefixes are 2-3 chars to leave headroom under Telegram's 64-byte
callback_data limit.
"""

from aiogram.filters.callback_data import CallbackData


class ServiceCB(CallbackData, prefix="svc"):
    service_id: str


class MasterCB(CallbackData, prefix="mst"):
    master_id: str


class DateCB(CallbackData, prefix="dt"):
    iso_date: str  # YYYY-MM-DD


class SlotCB(CallbackData, prefix="sl"):
    # The ISO datetime contains ":" which collides with CallbackData's default
    # separator. We carry only HH:MM as an int (1030 = 10:30); the date lives in
    # FSM data under "iso_date" and is combined at handler time.
    time_hhmm: int


class BookingActionCB(CallbackData, prefix="ba"):
    booking_id: str
    action: str  # confirm | cancel | reschedule


class NavCB(CallbackData, prefix="nv"):
    """Generic navigation/noop button (back, cancel, no-op variants).

    Keeping these out of the data factories prevents polluting them
    with action enums for non-data buttons. `noop_*` variants exist
    because Telegram doesn't truly disable inline buttons — tapping
    must answer the callback or the spinner hangs.
    """

    action: str  # back | cancel | confirm | noop_date | noop_header | noop_empty
