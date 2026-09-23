"""Настройки приложения из переменных окружения (.env).

Всё секретное (токен, ключи, API hash) живёт только здесь и только
из окружения. В коде нет ни одного реального значения.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram Bot ---
    bot_token: SecretStr
    # Список через запятую: ADMIN_IDS=111,222. Это «владельцы» —
    # их нельзя снять из админки. Остальных админов добавляют в панели.
    admin_ids: str = ""

    # --- База данных ---
    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    db_echo: bool = False

    # --- FSM-хранилище (необязательно) ---
    # Если задан — состояния диалогов переживают перезапуск.
    redis_url: str | None = None

    # --- Поддержка ---
    support_max_tickets: int = Field(default=3, ge=1, le=50)
    # Юзернейм человека/аккаунта поддержки для ссылки «написать в ЛС»
    # (без @). Используется в ссылке t.me/<username>?text=...
    support_username: str = ""

    # --- Портфолио (начальные значения, дальше меняются в админке) ---
    portfolio_url: str = ""
    portfolio_channel_url: str = ""
    community_chat_url: str = ""

    # --- Дополнительный аккаунт (Telethon) ---
    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    # Ключ Fernet для шифрования session string. Сгенерировать:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    session_encryption_key: SecretStr | None = None

    # --- Premium Emoji ---
    # Кастомные эмодзи в сообщениях бота Telegram разрешает не всем ботам.
    # Если Telegram откажет, бот сам откатится на обычные эмодзи.
    premium_emoji_enabled: bool = True

    # --- Прочее ---
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    log_dir: str = "logs"
    health_host: str = "0.0.0.0"
    health_port: int = 8080
    # Сколько сообщений в секунду отправлять при рассылке.
    # Лимит Telegram — около 30/сек, берём с запасом.
    broadcast_rate: float = Field(default=20.0, gt=0, le=30)

    @field_validator("support_username")
    @classmethod
    def _strip_at(cls, value: str) -> str:
        return value.strip().lstrip("@")

    @property
    def owner_ids(self) -> frozenset[int]:
        ids: set[int] = set()
        for chunk in self.admin_ids.replace(";", ",").split(","):
            chunk = chunk.strip()
            if chunk.lstrip("-").isdigit():
                ids.add(int(chunk))
        return frozenset(ids)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def telethon_enabled(self) -> bool:
        return bool(
            self.telegram_api_id
            and self.telegram_api_hash
            and self.telegram_api_hash.get_secret_value()
            and self.session_encryption_key
            and self.session_encryption_key.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
