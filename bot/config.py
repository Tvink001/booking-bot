"""Runtime configuration via pydantic-settings v2.

Reads from `.env` locally and environment variables in production. Provides
typed access to every variable from project_specs.md §3.1. Secrets typed as
`SecretStr` to keep them out of logs and repr by default.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    bot_token: SecretStr
    webhook_secret: SecretStr
    webhook_base_url: str = "https://example.com"
    owner_telegram_chat_id: int
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # Google
    google_service_account_path: Path = Path("./secrets/credentials.json")
    google_sheet_id: str
    google_calendar_default_tz: str = "Europe/Kyiv"

    # Groq
    groq_api_key: SecretStr

    # Mode / web server
    mode: Literal["polling", "webhook"] = "polling"
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Scheduler
    # If `scheduler_db_url` is set, it takes precedence — used for production
    # (Postgres via asyncpg). Local dev leaves it unset and falls back to a
    # SQLite file at `scheduler_db_path`. URL form:
    #   postgresql+asyncpg://user:pass@host:port/db
    scheduler_db_url: SecretStr | None = None
    scheduler_db_path: Path = Path("./data/scheduler.db")
    scheduler_timezone: str = "Europe/Kyiv"

    # Logging
    log_level: str = "INFO"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v


settings = Settings()  # type: ignore[call-arg]
