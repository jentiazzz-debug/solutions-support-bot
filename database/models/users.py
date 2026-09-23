from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, TimestampMixin, utcnow


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    # Пользователь заблокировал бота (узнаём при рассылке/ответе).
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Тикет, в который сейчас уходят сообщения пользователя.
    active_ticket_id: Mapped[int | None] = mapped_column(Integer)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or "Без имени"

    @property
    def mention(self) -> str:
        return f"@{self.username}" if self.username else self.full_name


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    # Получать ли уведомления о новых тикетах в бота.
    notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(128))


class BannedUser(TimestampMixin, Base):
    __tablename__ = "banned_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    reason: Mapped[str | None] = mapped_column(Text)
    banned_by: Mapped[int | None] = mapped_column(BigInteger)
