"""Tests for `bot.services.whisper.WhisperService`.

The Groq SDK is mocked via `AsyncMock` on the chained
`client.audio.transcriptions.create` call. `__init__` is bypassed via
`__new__` so the test doesn't need a real GROQ_API_KEY (same pattern as
tests/test_calendar_cache.py).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.whisper import WhisperService


@pytest.fixture
def whisper_with_mock() -> tuple[WhisperService, AsyncMock]:
    """WhisperService with a mocked AsyncGroq client.

    Returns the service plus the bound AsyncMock for `transcriptions.create`
    so each test can configure return_value / side_effect and assert calls.
    """
    ws = WhisperService.__new__(WhisperService)
    client = MagicMock()
    create = AsyncMock(return_value="Артем\n")
    client.audio.transcriptions.create = create
    ws._client = client
    return ws, create


async def test_transcribe_strips_whitespace(
    whisper_with_mock: tuple[WhisperService, AsyncMock],
) -> None:
    ws, create = whisper_with_mock
    create.return_value = "  Артем\n"
    result = await ws.transcribe(b"audio-bytes")
    assert result == "Артем"


async def test_transcribe_passes_expected_sdk_args(
    whisper_with_mock: tuple[WhisperService, AsyncMock],
) -> None:
    """SDK invocation must use the verified model id, OGG mimetype tuple,
    and `response_format='text'` per project_specs.md §9.4."""
    ws, create = whisper_with_mock
    audio = b"\x00\x01\x02"
    await ws.transcribe(audio, language="ru")

    create.assert_awaited_once()
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "whisper-large-v3-turbo"
    assert kwargs["language"] == "ru"
    assert kwargs["response_format"] == "text"
    filename, contents, mimetype = kwargs["file"]
    assert filename == "voice.ogg"
    assert contents == audio
    assert mimetype == "audio/ogg"


async def test_transcribe_propagates_sdk_exception(
    whisper_with_mock: tuple[WhisperService, AsyncMock],
) -> None:
    """Hard SDK failures must bubble up so the handler can decide to log
    to _errors AND show a friendly fallback message."""
    ws, create = whisper_with_mock
    create.side_effect = RuntimeError("Groq 5xx")
    with pytest.raises(RuntimeError, match="Groq 5xx"):
        await ws.transcribe(b"audio")


async def test_transcribe_handles_object_response_with_str(
    whisper_with_mock: tuple[WhisperService, AsyncMock],
) -> None:
    """If the SDK returns a non-str object (older shapes, future changes),
    `str(resp).strip()` still yields the text. Defensive against drift."""
    ws, create = whisper_with_mock

    class _ObjResponse:
        def __str__(self) -> str:
            return "  Артем  "

    create.return_value = _ObjResponse()
    result = await ws.transcribe(b"audio")
    assert result == "Артем"
