"""Groq Whisper async wrapper for voice name transcription (WOW 3).

See project_specs.md §17 + §9.4. Groq is used instead of OpenAI per §2.1
(permanent free tier, newer Whisper-Large-v3-turbo model, identical SDK
shape). Context7-verified against /groq/groq-python May 2026.

Init takes no args (reads `settings.groq_api_key` directly) — consistent
with SheetsService / CalendarService construction patterns.
"""

import logging

from groq import AsyncGroq

from bot.config import settings

logger = logging.getLogger(__name__)

_MODEL = "whisper-large-v3-turbo"
_DEFAULT_LANG = "ru"
_DEFAULT_MIMETYPE = "audio/ogg"
_DEFAULT_FILENAME = "voice.ogg"


class WhisperService:
    """Thin async wrapper over Groq's audio.transcriptions.create."""

    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key.get_secret_value())

    async def transcribe(
        self,
        file_bytes: bytes,
        language: str = _DEFAULT_LANG,
        filename: str = _DEFAULT_FILENAME,
        mimetype: str = _DEFAULT_MIMETYPE,
    ) -> str:
        """Transcribe a voice clip. Returns stripped text.

        Raises whatever the Groq SDK raises (APIError, network, 4xx/5xx)
        so the caller can decide which failures route to `_errors` and
        which are soft user-flow events. Telegram voice messages are
        OGG/OPUS — Groq accepts them natively without transcoding.
        """
        resp = await self._client.audio.transcriptions.create(
            model=_MODEL,
            file=(filename, file_bytes, mimetype),
            language=language,
            response_format="text",
        )
        return str(resp).strip()
