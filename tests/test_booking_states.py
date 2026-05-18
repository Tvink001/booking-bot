"""FSM transition tests for the booking flow.

These tests drive FSMContext directly (no handler invocation, no Bot,
no Sheets/Calendar I/O). They assert that the state machine progresses
through the 6 states as expected and that FSMContext data accumulates
in the documented shape (project_specs.md §11).
"""

from datetime import datetime

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.states import Booking


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=0, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_initial_state_is_none(state: FSMContext) -> None:
    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_full_happy_path_data_shape(state: FSMContext) -> None:
    # 1. Enter booking flow at service picker
    await state.set_state(Booking.choosing_service)
    assert await state.get_state() == Booking.choosing_service.state

    # 2. Pick service
    await state.update_data(service_id="haircut-30")
    await state.set_state(Booking.choosing_master)
    assert await state.get_data() == {"service_id": "haircut-30"}

    # 3. Pick master
    await state.update_data(master_id="m1")
    await state.set_state(Booking.choosing_date)
    data = await state.get_data()
    assert data == {"service_id": "haircut-30", "master_id": "m1"}

    # 4. Pick date
    await state.update_data(iso_date="2026-05-20")
    await state.set_state(Booking.choosing_slot)
    data = await state.get_data()
    assert data["iso_date"] == "2026-05-20"

    # 5. Pick slot
    iso_dt = datetime(2026, 5, 20, 11, 0).isoformat()
    await state.update_data(iso_datetime=iso_dt)
    await state.set_state(Booking.entering_contact)
    data = await state.get_data()
    assert data["iso_datetime"] == iso_dt

    # 6a. Enter name (sub-step 1 of entering_contact)
    await state.update_data(client_name="Анна")
    data = await state.get_data()
    assert "client_name" in data and "client_phone" not in data

    # 6b. Enter phone (sub-step 2)
    await state.update_data(client_phone="+380501234567")
    data = await state.get_data()
    assert data["client_phone"] == "+380501234567"

    # 7. Confirm step
    await state.set_state(Booking.confirming)
    assert await state.get_state() == Booking.confirming.state

    # Final data shape carries everything for the atomic confirmation
    final = await state.get_data()
    assert set(final.keys()) == {
        "service_id",
        "master_id",
        "iso_date",
        "iso_datetime",
        "client_name",
        "client_phone",
    }

    # Clear after success
    await state.clear()
    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_back_navigation_preserves_data(state: FSMContext) -> None:
    """Back from confirming → entering_contact drops phone but keeps name."""
    await state.set_state(Booking.confirming)
    await state.update_data(
        service_id="haircut-30",
        master_id="m1",
        iso_date="2026-05-20",
        iso_datetime="2026-05-20T11:00:00",
        client_name="Анна",
        client_phone="+380501234567",
    )

    # Simulate back-from-confirming as the handler does
    data = await state.get_data()
    new_data = {k: v for k, v in data.items() if k != "client_phone"}
    await state.set_data(new_data)
    await state.set_state(Booking.entering_contact)

    final = await state.get_data()
    assert final["client_name"] == "Анна"
    assert "client_phone" not in final


async def test_back_from_entering_contact_drops_contact_and_slot(
    state: FSMContext,
) -> None:
    """Back from entering_contact → choosing_slot drops name + phone + slot."""
    await state.set_state(Booking.entering_contact)
    await state.update_data(
        service_id="haircut-30",
        master_id="m1",
        iso_date="2026-05-20",
        iso_datetime="2026-05-20T11:00:00",
        client_name="Анна",
    )

    data = await state.get_data()
    new_data = {
        k: v for k, v in data.items() if k not in ("client_name", "client_phone", "iso_datetime")
    }
    await state.set_data(new_data)
    await state.set_state(Booking.choosing_slot)

    final = await state.get_data()
    assert final == {
        "service_id": "haircut-30",
        "master_id": "m1",
        "iso_date": "2026-05-20",
    }


async def test_cancel_clears_everything(state: FSMContext) -> None:
    await state.set_state(Booking.confirming)
    await state.update_data(service_id="haircut-30", client_name="Анна")
    await state.clear()
    assert await state.get_state() is None
    assert await state.get_data() == {}
