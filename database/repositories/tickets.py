from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import Select, func, select, update

from database.models import (
    ACTIVE_STATUSES,
    Ticket,
    TicketCategory,
    TicketMessage,
    TicketMessageLink,
    TicketStatus,
)
from database.repositories.base import OrderedRepository, Repository


class CategoryRepository(OrderedRepository[TicketCategory]):
    model = TicketCategory


@dataclass(slots=True)
class TicketFilter:
    status: str | None = None  # None — все
    ticket_id: int | None = None
    user_id: int | None = None
    username: str | None = None
    category: str | None = None

    @property
    def is_search(self) -> bool:
        return any((self.ticket_id, self.user_id, self.username, self.category))


class TicketRepository(Repository[Ticket]):
    model = Ticket

    async def count_active_for_user(self, user_id: int) -> int:
        return await self.session.scalar(
            select(func.count(Ticket.id)).where(
                Ticket.user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES)
            )
        ) or 0

    async def active_for_user(self, user_id: int) -> Sequence[Ticket]:
        return (
            await self.session.scalars(
                select(Ticket)
                .where(Ticket.user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES))
                .order_by(Ticket.last_message_at.desc())
            )
        ).all()

    async def recent_for_user(self, user_id: int, limit: int = 10) -> Sequence[Ticket]:
        return (
            await self.session.scalars(
                select(Ticket)
                .where(Ticket.user_id == user_id)
                .order_by(Ticket.id.desc())
                .limit(limit)
            )
        ).all()

    async def count_for_user(self, user_id: int) -> int:
        return await self.session.scalar(
            select(func.count(Ticket.id)).where(Ticket.user_id == user_id)
        ) or 0

    def _filtered(self, flt: TicketFilter) -> Select:
        stmt = select(Ticket)
        if flt.status:
            stmt = stmt.where(Ticket.status == flt.status)
        if flt.ticket_id is not None:
            stmt = stmt.where(Ticket.id == flt.ticket_id)
        if flt.user_id is not None:
            stmt = stmt.where(Ticket.user_id == flt.user_id)
        if flt.username:
            stmt = stmt.where(func.lower(Ticket.username) == flt.username.lstrip("@").lower())
        if flt.category:
            stmt = stmt.where(func.lower(Ticket.category_title).contains(flt.category.lower()))
        return stmt

    async def page(
        self, flt: TicketFilter, offset: int, limit: int
    ) -> tuple[Sequence[Ticket], int]:
        base = self._filtered(flt)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = await self.session.scalars(
            base.order_by(Ticket.last_message_at.desc(), Ticket.id.desc()).offset(offset).limit(limit)
        )
        return rows.all(), total

    async def active_ids_for_user(self, user_id: int) -> list[int]:
        return list(
            await self.session.scalars(
                select(Ticket.id).where(
                    Ticket.user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES)
                )
            )
        )

    async def set_status_for_user(self, user_id: int, status: TicketStatus, **fields) -> None:
        await self.session.execute(
            update(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES))
            .values(status=status.value, **fields)
        )

    # --- сообщения ---

    async def add_message(self, message: TicketMessage) -> TicketMessage:
        self.session.add(message)
        await self.session.flush()
        return message

    async def messages(
        self, ticket_id: int, offset: int = 0, limit: int = 50, newest_first: bool = False
    ) -> Sequence[TicketMessage]:
        order = TicketMessage.id.desc() if newest_first else TicketMessage.id
        return (
            await self.session.scalars(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == ticket_id)
                .order_by(order)
                .offset(offset)
                .limit(limit)
            )
        ).all()

    async def media_messages(self, ticket_id: int, limit: int = 30) -> Sequence[TicketMessage]:
        return (
            await self.session.scalars(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == ticket_id, TicketMessage.file_id.is_not(None))
                .order_by(TicketMessage.id)
                .limit(limit)
            )
        ).all()

    async def count_messages(self, ticket_id: int | None = None) -> int:
        stmt = select(func.count(TicketMessage.id))
        if ticket_id is not None:
            stmt = stmt.where(TicketMessage.ticket_id == ticket_id)
        return await self.session.scalar(stmt) or 0

    async def count_media(self, ticket_id: int) -> int:
        return await self.session.scalar(
            select(func.count(TicketMessage.id)).where(
                TicketMessage.ticket_id == ticket_id, TicketMessage.file_id.is_not(None)
            )
        ) or 0

    # --- связи сообщений с тикетами ---

    async def link(self, ticket_id: int, chat_id: int, message_id: int) -> None:
        exists = await self.session.scalar(
            select(TicketMessageLink.id).where(
                TicketMessageLink.chat_id == chat_id, TicketMessageLink.message_id == message_id
            )
        )
        if exists is None:
            self.session.add(
                TicketMessageLink(ticket_id=ticket_id, chat_id=chat_id, message_id=message_id)
            )
            await self.session.flush()

    async def by_link(self, chat_id: int, message_id: int) -> Ticket | None:
        ticket_id = await self.session.scalar(
            select(TicketMessageLink.ticket_id).where(
                TicketMessageLink.chat_id == chat_id, TicketMessageLink.message_id == message_id
            )
        )
        return await self.get(ticket_id) if ticket_id is not None else None

    # --- статистика ---

    async def count(self, status: str | None = None) -> int:
        stmt = select(func.count(Ticket.id))
        if status:
            stmt = stmt.where(Ticket.status == status)
        return await self.session.scalar(stmt) or 0

    async def count_by_status(self) -> dict[str, int]:
        rows = await self.session.execute(select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status))
        return {status: count for status, count in rows.all()}

    async def created_dates_since(self, since: datetime) -> Sequence[datetime]:
        return (
            await self.session.scalars(select(Ticket.created_at).where(Ticket.created_at >= since))
        ).all()

    async def count_by_category(self) -> list[tuple[str, int]]:
        rows = await self.session.execute(
            select(Ticket.category_title, func.count(Ticket.id))
            .group_by(Ticket.category_title)
            .order_by(func.count(Ticket.id).desc())
        )
        return [(title or "—", count) for title, count in rows.all()]
