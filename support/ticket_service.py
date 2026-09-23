"""Бизнес-логика тикетов: создание, переписка, закрытие, блокировка.

Хендлеры только разбирают апдейты и вызывают методы этого сервиса.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import Message

from bot.context import AppContext
from bot.keyboards.tickets import (
    admin_incoming_kb,
    new_ticket_kb,
    user_after_close_kb,
    user_incoming_kb,
)
from config import emoji as E
from database.models import (
    QuickReply,
    SenderType,
    Ticket,
    TicketCategory,
    TicketMessage,
    TicketStatus,
    User,
    utcnow,
)
from database.repositories import Repo
from support.deeplink import admin_ticket_link
from support.message_service import Content, extract, relay, send_stored, with_retry
from utils.text import esc, fmt_time, truncate

log = logging.getLogger(__name__)

_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


class TicketError(Exception):
    """Ошибка, текст которой можно показать пользователю/админу."""


class UserUnreachable(TicketError):
    pass


class TicketService:
    def __init__(self, bot: Bot, repo: Repo, ctx: AppContext) -> None:
        self.bot = bot
        self.repo = repo
        self.ctx = ctx
        self.tz = ctx.settings.tz

    # ------------------------------------------------------------ лимиты

    async def max_tickets(self) -> int:
        raw = await self.repo.settings.get("max_tickets")
        if raw and raw.isdigit() and int(raw) > 0:
            return int(raw)
        return self.ctx.settings.support_max_tickets

    async def creation_error(self, user_id: int) -> str | None:
        """Текст причины, по которой нельзя создать тикет, или None."""
        if await self.repo.bans.is_banned(user_id):
            return f"{E.BAN_EMOJI} Доступ к поддержке для вас ограничен."
        limit = await self.max_tickets()
        if await self.repo.tickets.count_active_for_user(user_id) >= limit:
            return (
                f"{E.WARNING_EMOJI} Вы достигли максимального количества активных обращений — "
                f"<b>{limit}</b>.\n\nНовый тикет создать нельзя, пока один из предыдущих "
                "не будет закрыт."
            )
        return None

    # ------------------------------------------------------------ получатели

    async def _admin_recipients(self, ticket: Ticket | None = None) -> list[int]:
        if ticket is not None and ticket.assigned_admin_id and self.ctx.admins.is_admin(
            ticket.assigned_admin_id
        ):
            return [ticket.assigned_admin_id]
        muted = {a.user_id for a in await self.repo.admins.all() if not a.notify}
        return sorted(self.ctx.admins.all_ids - muted)

    # ------------------------------------------------------------ хранение

    async def _store(
        self,
        ticket: Ticket,
        sender: SenderType,
        sender_id: int | None,
        content: Content,
        message: Message | None = None,
    ) -> TicketMessage:
        ticket.last_message_at = utcnow()
        return await self.repo.tickets.add_message(
            TicketMessage(
                ticket_id=ticket.id,
                sender_type=sender.value,
                sender_id=sender_id,
                content_type=content.content_type,
                text=content.text,
                html=content.html,
                file_id=content.file_id,
                source_chat_id=message.chat.id if message else None,
                source_message_id=message.message_id if message else None,
            )
        )

    async def _system(self, ticket: Ticket, text: str) -> None:
        await self._store(ticket, SenderType.SYSTEM, None, Content("text", text, esc(text)))

    # ------------------------------------------------------------ создание

    async def create(self, user: User, category: TicketCategory, first: Message) -> Ticket:
        error = await self.creation_error(user.id)
        if error:
            raise TicketError(error)
        content = extract(first)
        if content is None:
            raise TicketError("Этот тип сообщения нельзя отправить в поддержку.")

        ticket = Ticket(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            category_id=category.id,
            category_title=category.title,
            status=TicketStatus.OPEN.value,
        )
        await self.repo.tickets.add(ticket)
        await self._store(ticket, SenderType.USER, user.id, content, first)
        await self.repo.users.set_active_ticket(user.id, ticket.id)
        await self.repo.commit()
        log.info("Создан тикет %s пользователем %s (%s)", ticket.number, user.id, category.title)

        await self._notify_new(ticket, first)
        return ticket

    def new_ticket_text(self, ticket: Ticket) -> str:
        username = f"@{esc(ticket.username)}" if ticket.username else esc(ticket.full_name)
        return (
            f"{E.BELL_EMOJI} <b>Новый тикет {ticket.number}</b>\n\n"
            f"{E.USER_EMOJI} Пользователь: {username} "
            f"(<code>{ticket.user_id}</code>)\n"
            f"{E.CATEGORY_EMOJI} Категория: {esc(ticket.category_title)}\n"
            f"{E.TIME_EMOJI} Время: {fmt_time(ticket.created_at, self.tz)}"
        )

    async def _notify_new(self, ticket: Ticket, first: Message) -> None:
        text = self.new_ticket_text(ticket)
        for admin_id in await self._admin_recipients():
            try:
                card = await with_retry(
                    lambda: self.bot.send_message(admin_id, text, reply_markup=new_ticket_kb(ticket))
                )
                await self.repo.tickets.link(ticket.id, admin_id, card.message_id)
                copy_id = await relay(
                    self.bot, first, admin_id, reply_markup=admin_incoming_kb(ticket)
                )
                await self.repo.tickets.link(ticket.id, admin_id, copy_id)
            except TelegramAPIError as error:
                log.warning("Не удалось уведомить админа %s: %s", admin_id, error)
        await self.repo.commit()

        # Доп. аккаунт — в фоне: медленный MTProto не должен задерживать ответ пользователю.
        if self.ctx.accounts.available:
            username = f"@{esc(ticket.username)}" if ticket.username else esc(ticket.full_name)
            link = admin_ticket_link(self.ctx.bot_username, ticket.id) if self.ctx.bot_username else ""
            content = extract(first)
            preview = esc(truncate(content.preview(200), 200)) if content else ""
            html = (
                f"🔔 <b>Новый тикет {ticket.number}</b>\n"
                f"👤 {username}\n"
                f"📁 {esc(ticket.category_title)}\n"
                + (f"\n💬 {preview}\n" if preview else "")
                + (f'\n<a href="{link}">Открыть тикет →</a>' if link else "")
            )
            _spawn(self.ctx.accounts.notify_all(html))

    # ------------------------------------------------------------ переписка

    async def user_message(self, ticket: Ticket, message: Message) -> None:
        if not ticket.is_active:
            raise TicketError(f"Обращение {ticket.number} уже закрыто.")
        content = extract(message)
        if content is None:
            raise TicketError("Этот тип сообщения нельзя отправить в поддержку.")
        await self._store(ticket, SenderType.USER, message.from_user.id if message.from_user else None,
                          content, message)
        await self.repo.users.set_active_ticket(ticket.user_id, ticket.id)
        await self.repo.commit()

        delivered = 0
        for admin_id in await self._admin_recipients(ticket):
            try:
                copy_id = await relay(self.bot, message, admin_id, reply_markup=admin_incoming_kb(ticket))
                await self.repo.tickets.link(ticket.id, admin_id, copy_id)
                delivered += 1
            except TelegramAPIError as error:
                log.warning("Сообщение тикета %s не доставлено админу %s: %s", ticket.number, admin_id, error)
        await self.repo.commit()
        if not delivered:
            log.error("Сообщение тикета %s не доставлено ни одному админу", ticket.number)

    async def admin_message(self, ticket: Ticket, admin_id: int, message: Message) -> None:
        if ticket.status == TicketStatus.BANNED.value:
            raise TicketError("Пользователь заблокирован — ответ не отправлен.")
        content = extract(message)
        if content is None:
            raise TicketError("Этот тип сообщения нельзя отправить.")
        try:
            copy_id = await relay(self.bot, message, ticket.user_id, reply_markup=user_incoming_kb(ticket))
        except TelegramForbiddenError as error:
            await self.repo.users.set_blocked_bot(ticket.user_id, True)
            await self.repo.commit()
            raise UserUnreachable("Пользователь заблокировал бота — сообщение не доставлено.") from error
        await self.repo.tickets.link(ticket.id, ticket.user_id, copy_id)
        await self._store(ticket, SenderType.ADMIN, admin_id, content, message)
        await self._mark_answered(ticket, admin_id)
        await self.repo.commit()

    async def send_quick_reply(self, ticket: Ticket, admin_id: int, quick: QuickReply) -> None:
        if ticket.status == TicketStatus.BANNED.value:
            raise TicketError("Пользователь заблокирован — ответ не отправлен.")
        try:
            sent = await send_stored(
                self.bot, ticket.user_id, quick.content_type, quick.html, quick.file_id,
                reply_markup=user_incoming_kb(ticket),
            )
        except TelegramForbiddenError as error:
            await self.repo.users.set_blocked_bot(ticket.user_id, True)
            await self.repo.commit()
            raise UserUnreachable("Пользователь заблокировал бота — сообщение не доставлено.") from error
        await self.repo.tickets.link(ticket.id, ticket.user_id, sent.message_id)
        content = extract(sent) or Content(quick.content_type, None, quick.html, quick.file_id)
        await self._store(ticket, SenderType.ADMIN, admin_id, content, None)
        await self._mark_answered(ticket, admin_id)
        await self.repo.commit()

    async def _mark_answered(self, ticket: Ticket, admin_id: int) -> None:
        if ticket.status == TicketStatus.OPEN.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
        if ticket.assigned_admin_id is None:
            ticket.assigned_admin_id = admin_id

    async def take(self, ticket: Ticket, admin_id: int) -> None:
        ticket.assigned_admin_id = admin_id
        if ticket.status == TicketStatus.OPEN.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
        await self._system(ticket, f"Тикет взят в работу администратором {admin_id}")
        await self.repo.commit()

    # ------------------------------------------------------------ закрытие

    async def close(
        self, ticket: Ticket, closed_by: int, reason: str | None = None, by_user: bool = False
    ) -> None:
        if not ticket.is_active:
            raise TicketError(f"Тикет {ticket.number} уже закрыт.")
        ticket.status = TicketStatus.CLOSED.value
        ticket.closed_at = utcnow()
        ticket.closed_by = closed_by
        ticket.close_reason = reason
        await self._system(
            ticket,
            ("Закрыт пользователем" if by_user else "Закрыт администратором")
            + (f". Причина: {reason}" if reason else ""),
        )
        user = await self.repo.users.get(ticket.user_id)
        if user is not None and user.active_ticket_id == ticket.id:
            user.active_ticket_id = None
        await self.repo.commit()

        if by_user:
            for admin_id in await self._admin_recipients(ticket):
                await self._safe_send(
                    admin_id, f"{E.CLOSE_EMOJI} Пользователь закрыл тикет <b>{ticket.number}</b>."
                )
        else:
            text = f"{E.CLOSE_EMOJI} Ваше обращение <b>{ticket.number}</b> закрыто."
            if reason:
                text += f"\nПричина: {esc(reason)}"
            text += "\n\nЕсли вопрос остался — создайте новое обращение."
            await self._safe_send(ticket.user_id, text, reply_markup=user_after_close_kb())

    async def _safe_send(self, chat_id: int, text: str, **kwargs) -> bool:
        try:
            await with_retry(lambda: self.bot.send_message(chat_id, text, **kwargs))
            return True
        except TelegramForbiddenError:
            await self.repo.users.set_blocked_bot(chat_id, True)
            await self.repo.commit()
        except TelegramAPIError as error:
            log.warning("Не удалось отправить сообщение %s: %s", chat_id, error)
        return False

    # ------------------------------------------------------------ блокировка

    async def ban(self, user_id: int, admin_id: int, reason: str | None = None) -> int:
        """Заблокировать в поддержке. Возвращает число закрытых активных тикетов."""
        if self.ctx.admins.is_admin(user_id):
            raise TicketError("Нельзя заблокировать администратора.")
        await self.repo.bans.ban(user_id, reason, admin_id)
        active = await self.repo.tickets.active_ids_for_user(user_id)
        await self.repo.tickets.set_status_for_user(
            user_id,
            TicketStatus.BANNED,
            closed_at=utcnow(),
            closed_by=admin_id,
            close_reason=reason or "Пользователь заблокирован",
        )
        await self.repo.users.set_active_ticket(user_id, None)
        await self.repo.commit()
        text = f"{E.BAN_EMOJI} Доступ к поддержке для вас ограничен."
        if reason:
            text += f"\nПричина: {esc(reason)}"
        await self._safe_send(user_id, text)
        log.info("Пользователь %s заблокирован админом %s", user_id, admin_id)
        return len(active)

    async def unban(self, user_id: int) -> bool:
        ok = await self.repo.bans.unban(user_id)
        await self.repo.commit()
        if ok:
            await self._safe_send(user_id, f"{E.UNLOCK_EMOJI} Доступ к поддержке восстановлен.")
        return ok
