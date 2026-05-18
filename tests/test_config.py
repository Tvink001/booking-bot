"""Smoke test for bot.config.Settings."""

from pathlib import Path


def test_settings_loads(env_for_settings: None) -> None:
    from bot.config import Settings

    s = Settings()
    assert s.bot_token.get_secret_value() == "123456:test-token"
    assert s.webhook_secret.get_secret_value().startswith("test-secret-")
    assert s.owner_telegram_chat_id == -1001234567890
    assert s.admin_telegram_ids == [123456789, 987654321]
    assert s.google_service_account_path == Path("./secrets/credentials.json")
    assert s.google_sheet_id == "test-sheet-id"
    assert s.mode == "polling"
    assert s.web_port == 8080
