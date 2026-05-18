"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest


@pytest.fixture
def env_for_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set a complete set of env vars so Settings() constructs without errors.

    Env vars take precedence over .env, so this fixture isolates tests from
    whatever happens to be in the operator's local .env.
    """
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret-32-chars-long-aaaaaaaaaaaa")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.com")
    monkeypatch.setenv("OWNER_TELEGRAM_CHAT_ID", "-1001234567890")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "123456789,987654321")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_PATH", "./secrets/credentials.json")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "test-sheet-id")
    monkeypatch.setenv("GOOGLE_CALENDAR_DEFAULT_TZ", "Europe/Kyiv")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("MODE", "polling")
    monkeypatch.setenv("WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("WEB_PORT", "8080")
    monkeypatch.setenv("SCHEDULER_DB_PATH", "./data/scheduler.db")
    monkeypatch.setenv("SCHEDULER_TIMEZONE", "Europe/Kyiv")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    yield
