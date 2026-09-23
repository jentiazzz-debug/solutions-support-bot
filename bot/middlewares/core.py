from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser

from bot.context import AppContext
from database.repositories import Repo
from support.ticket_service import TicketService

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию БД на апдейт и кладёт в data: repo, ctx, tickets."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.ctx.db.session() as session:
            repo = Repo(session)
            bot: Bot = data["bot"]
            data["repo"] = repo
            data["ctx"] = self.ctx
            data["tickets"] = TicketService(bot, repo, self.ctx)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class UserMiddleware(BaseMiddleware):
    """Регистрирует/обновляет пользователя, кладёт в data: user, is_admin, is_owner."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot or (chat is not None and chat.type != "private"):
            return None  # бот работает только в личных сообщениях
        repo: Repo = data["repo"]
        ctx: AppContext = data["ctx"]
        user, is_new = await repo.users.upsert(
            tg_user.id,
            tg_user.username,
            tg_user.first_name,
            tg_user.last_name,
            tg_user.language_code,
        )
        # Короткая транзакция: фиксируем сразу, чтобы не держать блокировку строки
        # пользователя, пока хендлер ждёт (например, per-user lock при альбоме).
        await repo.commit()
        if is_new:
            log.info("Новый пользователь %s (@%s)", tg_user.id, tg_user.username)
        data["user"] = user
        data["is_admin"] = ctx.admins.is_admin(tg_user.id)
        data["is_owner"] = ctx.admins.is_owner(tg_user.id)
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Простой антифлуд для обычных пользователей: не больше N событий за окно."""

    def __init__(self, limit: int = 20, window: float = 30.0) -> None:
        self.limit = limit
        self.window = window
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._warned: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if data.get("is_admin"):
            return await handler(event, data)
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)
        now = time.monotonic()
        queue = self._events[tg_user.id]
        while queue and now - queue[0] > self.window:
            queue.popleft()
        if len(queue) >= self.limit:
            if now - self._warned.get(tg_user.id, 0) > self.window:
                self._warned[tg_user.id] = now
                text = "Слишком много сообщений. Подождите немного 🙏"
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=False)
            elif isinstance(event, CallbackQuery):
                await event.answer()
            return None
        queue.append(now)
        if len(self._events) > 10000:  # не копим память на старых пользователях
            for uid in [u for u, q in self._events.items() if not q or now - q[-1] > self.window]:
                self._events.pop(uid, None)
        return await handler(event, data)
