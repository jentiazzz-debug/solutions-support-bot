from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, TimestampMixin, utcnow


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bot_username: Mapped[str | None] = mapped_column(String(64))
    users_count: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(512))
    # [{"title": "...", "url": "..."}]
    extra_links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    image_file_id: Mapped[str | None] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def link(self) -> str | None:
        if self.url:
            return self.url
        if self.bot_username:
            return f"https://t.me/{self.bot_username.lstrip('@')}"
        return None


class PortfolioLink(TimestampMixin, Base):
    __tablename__ = "portfolio_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    icon_emoji_id: Mapped[str | None] = mapped_column(String(32))
    style: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MenuButton(TimestampMixin, Base):
    """Кнопка главного меню.

    key: about / support / portfolio — встроенные разделы;
    для пользовательских кнопок-ссылок key = "link" и заполнен url.
    """

    __tablename__ = "menu_buttons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(String(64), nullable=False)
    icon_emoji_id: Mapped[str | None] = mapped_column(String(32))
    # primary (синий) / success (зелёный) / danger (красный) / None (обычная)
    style: Mapped[str | None] = mapped_column(String(16))
    url: Mapped[str | None] = mapped_column(String(512))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Сколько кнопок в ряду: 1 — во всю ширину, 2 — половина.
    row_width: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class QuickReply(TimestampMixin, Base):
    __tablename__ = "quick_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    html: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Broadcast(TimestampMixin, Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    # [[{"text": "...", "url": "..."}, ...], ...] — ряды кнопок
    buttons: Mapped[list[list[dict[str, str]]]] = mapped_column(JSON, default=list, nullable=False)
    # draft / running / done / cancelled / interrupted
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BroadcastResult(TimestampMixin, Base):
    __tablename__ = "broadcast_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # sent / failed / blocked
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(String(256))


class ConnectedAccount(TimestampMixin, Base):
    """Дополнительный Telegram-аккаунт для уведомлений о тикетах.

    session_encrypted — StringSession Telethon, зашифрованная Fernet
    (ключ SESSION_ENCRYPTION_KEY в .env). В открытом виде нигде не лежит.
    """

    __tablename__ = "connected_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(128))
    phone_masked: Mapped[str | None] = mapped_column(String(32))
    session_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Куда слать уведомления: @username, числовой id или "me".
    notify_target: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
