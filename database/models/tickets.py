from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base, TimestampMixin, utcnow


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    BANNED = "BANNED"

    @property
    def is_active(self) -> bool:
        return self in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)


ACTIVE_STATUSES = (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)


class SenderType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class TicketCategory(TimestampMixin, Base):
    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}".strip()


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_user_status", "user_id", "status"),
        {"sqlite_autoincrement": True},
    )

    # Номера начинаются с 1001 (на PostgreSQL), чтобы выглядели как #1042.
    id: Mapped[int] = mapped_column(Integer, Identity(start=1001), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Снимок данных пользователя на момент создания.
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ticket_categories.id", ondelete="SET NULL")
    )
    category_title: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=TicketStatus.OPEN.value, nullable=False, index=True
    )
    assigned_admin_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(BigInteger)
    close_reason: Mapped[str | None] = mapped_column(Text)

    messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketMessage.id",
        lazy="noload",
    )

    @property
    def number(self) -> str:
        return f"#{self.id}"

    @property
    def status_enum(self) -> TicketStatus:
        return TicketStatus(self.status)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def user_mention(self) -> str:
        return f"@{self.username}" if self.username else (self.full_name or str(self.user_id))


class TicketMessage(TimestampMixin, Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_type: Mapped[str] = mapped_column(String(8), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # Текст/подпись: plain — для истории и поиска, html — для повторной отправки.
    text: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(256))
    source_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    source_message_id: Mapped[int | None] = mapped_column(Integer)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")


class TicketMessageLink(TimestampMixin, Base):
    """Какое сообщение в каком чате относится к какому тикету.

    Благодаря этому администратор (и пользователь) может просто нажать
    «Ответить» (reply) на сообщение — бот сам поймёт, в какой тикет.
    """

    __tablename__ = "ticket_message_links"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_ticket_link_chat_msg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
