"""AdminFilter + non-admin fallback handler tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.handlers.admin import (
    MSG_NO_RIGHTS,
    AdminFilter,
    on_admin_command_denied,
)


def _fake_message(user_id: int | None) -> Message:
    msg = MagicMock(spec=Message)
    if user_id is None:
        msg.from_user = None
    else:
        msg.from_user = MagicMock(id=user_id)
    return msg


async def test_admin_filter_admit_known_admin() -> None:
    flt = AdminFilter(admin_ids=[111, 222])
    msg = _fake_message(111)
    assert await flt(msg) is True


async def test_admin_filter_reject_non_admin() -> None:
    flt = AdminFilter(admin_ids=[111])
    msg = _fake_message(999)
    assert await flt(msg) is False


async def test_admin_filter_reject_missing_from_user() -> None:
    flt = AdminFilter(admin_ids=[111])
    msg = _fake_message(None)
    assert await flt(msg) is False


async def test_admin_filter_empty_admin_list_rejects_all() -> None:
    flt = AdminFilter(admin_ids=[])
    msg = _fake_message(111)
    assert await flt(msg) is False


async def test_non_admin_fallback_replies_no_rights() -> None:
    """The fallback handler that catches non-admins typing admin commands."""
    msg = _fake_message(999)
    msg.answer = AsyncMock()
    await on_admin_command_denied(msg)
    msg.answer.assert_awaited_once_with(MSG_NO_RIGHTS)


@pytest.fixture(autouse=True)
def _silence_pytest_asyncio_warning() -> None:
    """Anchor for asyncio fixtures even when none are needed by individual tests."""
    return None
