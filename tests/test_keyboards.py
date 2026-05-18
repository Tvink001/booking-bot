"""Keyboard builder tests — structure + callback_data pack/unpack roundtrip."""

from datetime import date, datetime

import pytest

from bot.callbacks import DateCB, MasterCB, NavCB, ServiceCB, SlotCB
from bot.keyboards.inline import (
    build_confirm_keyboard,
    build_date_keyboard,
    build_master_keyboard,
    build_service_keyboard,
    build_slot_keyboard,
)
from bot.models import Blackout, Master, Service


@pytest.fixture
def services() -> list[Service]:
    return [
        Service(
            id="haircut-30",
            name="Стрижка",
            duration_min=30,
            price=300,
            master_ids=[],
            is_active=True,
        ),
        Service(
            id="dance-60",
            name="Танцы",
            duration_min=60,
            price=500,
            master_ids=["m1"],
            is_active=True,
        ),
        Service(
            id="inactive",
            name="Неактивная",
            duration_min=30,
            price=0,
            master_ids=[],
            is_active=False,
        ),
    ]


@pytest.fixture
def masters() -> list[Master]:
    return [
        Master(
            id="m1",
            name="Анна",
            telegram_id=None,
            calendar_id="m1@example.com",
            work_hours="10:00-19:00",
            work_days=[1, 2, 3, 4, 5],
            is_active=True,
        ),
        Master(
            id="m2",
            name="Олег",
            telegram_id=None,
            calendar_id="m2@example.com",
            work_hours="12:00-20:00",
            work_days=[1, 2, 3, 4, 5, 6],
            is_active=True,
        ),
    ]


def test_service_keyboard_one_button_per_row_active_only(
    services: list[Service],
) -> None:
    kb = build_service_keyboard(services)
    # 2 active services (1 row each) + 1 cancel row
    assert len(kb.inline_keyboard) == 3
    for row in kb.inline_keyboard[:2]:
        assert len(row) == 1

    # Roundtrip callback_data
    btn = kb.inline_keyboard[0][0]
    assert btn.callback_data is not None
    parsed = ServiceCB.unpack(btn.callback_data)
    assert parsed.service_id == "haircut-30"

    # Cancel row uses NavCB
    cancel_btn = kb.inline_keyboard[-1][0]
    assert cancel_btn.callback_data is not None
    nav = NavCB.unpack(cancel_btn.callback_data)
    assert nav.action == "cancel"


def test_master_keyboard_filters_by_service_master_ids(
    masters: list[Master], services: list[Service]
) -> None:
    dance = services[1]  # restricted to ["m1"]
    kb = build_master_keyboard(masters, dance)
    # Only m1 + nav row
    assert len(kb.inline_keyboard) == 2
    btn = kb.inline_keyboard[0][0]
    assert btn.callback_data is not None
    parsed = MasterCB.unpack(btn.callback_data)
    assert parsed.master_id == "m1"


def test_master_keyboard_empty_master_ids_shows_all(
    masters: list[Master], services: list[Service]
) -> None:
    haircut = services[0]  # master_ids=[] → any master
    kb = build_master_keyboard(masters, haircut)
    # 2 masters + nav row
    assert len(kb.inline_keyboard) == 3


def test_date_keyboard_grid_layout_and_strike(masters: list[Master]) -> None:
    master = masters[0]  # work_days = Mon-Fri (1..5)
    # 2026-05-18 is Monday → first cell is workday
    start = date(2026, 5, 18)
    blackouts = [Blackout(master_id=master.id, date=date(2026, 5, 20), reason="x")]
    kb = build_date_keyboard(start, master, blackouts)
    # 2 rows of 7 + nav row = 3 rows
    assert len(kb.inline_keyboard) == 3
    assert len(kb.inline_keyboard[0]) == 7
    assert len(kb.inline_keyboard[1]) == 7

    # Mon 2026-05-18 (workday, no blackout) → DateCB
    mon_btn = kb.inline_keyboard[0][0]
    assert mon_btn.callback_data is not None
    parsed_mon = DateCB.unpack(mon_btn.callback_data)
    assert parsed_mon.iso_date == "2026-05-18"
    # Wed 2026-05-20 → blackout → NavCB noop_date
    wed_btn = kb.inline_keyboard[0][2]
    assert wed_btn.callback_data is not None
    parsed_wed = NavCB.unpack(wed_btn.callback_data)
    assert parsed_wed.action == "noop_date"
    # Sat 2026-05-23 → not in work_days → NavCB noop_date
    sat_btn = kb.inline_keyboard[0][5]
    assert sat_btn.callback_data is not None
    parsed_sat = NavCB.unpack(sat_btn.callback_data)
    assert parsed_sat.action == "noop_date"


def test_slot_keyboard_empty_state_has_back_button() -> None:
    kb = build_slot_keyboard([])
    # 1 row "нет слотов" + 1 row back
    assert len(kb.inline_keyboard) == 2
    empty_btn = kb.inline_keyboard[0][0]
    assert empty_btn.callback_data is not None
    parsed = NavCB.unpack(empty_btn.callback_data)
    assert parsed.action == "noop_empty"

    back_btn = kb.inline_keyboard[1][0]
    assert back_btn.callback_data is not None
    parsed = NavCB.unpack(back_btn.callback_data)
    assert parsed.action == "back"


def test_slot_keyboard_morning_afternoon_split() -> None:
    slots = [
        datetime(2026, 5, 18, 10, 0),
        datetime(2026, 5, 18, 10, 30),
        datetime(2026, 5, 18, 11, 0),
        datetime(2026, 5, 18, 14, 0),
        datetime(2026, 5, 18, 15, 30),
    ]
    kb = build_slot_keyboard(slots)
    # rows: morning header, 1 row of 3 morning slots, afternoon header,
    #       1 row of 2 afternoon slots, nav row = 5 rows
    assert len(kb.inline_keyboard) == 5
    # morning header is NavCB noop_header
    mh = kb.inline_keyboard[0][0]
    assert mh.callback_data is not None
    assert NavCB.unpack(mh.callback_data).action == "noop_header"
    # first morning slot — SlotCB encoding HH:MM as int (1000 = 10:00)
    slot_btn = kb.inline_keyboard[1][0]
    assert slot_btn.callback_data is not None
    parsed = SlotCB.unpack(slot_btn.callback_data)
    assert parsed.time_hhmm == 1000


def test_confirm_keyboard_two_buttons() -> None:
    kb = build_confirm_keyboard()
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 2
    confirm_btn = kb.inline_keyboard[0][0]
    cancel_btn = kb.inline_keyboard[0][1]
    assert confirm_btn.callback_data is not None
    assert cancel_btn.callback_data is not None
    assert NavCB.unpack(confirm_btn.callback_data).action == "confirm"
    assert NavCB.unpack(cancel_btn.callback_data).action == "cancel"
