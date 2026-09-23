"""Рассылка, устойчивая к лимитам Telegram.

• Скорость ограничена BROADCAST_RATE сообщ./сек (лимит Telegram ≈30/сек).
• На TelegramRetryAfter ждём столько, сколько просит Telegram, и повторяем
  того же получателя — никто не теряется.
• Заблокировавшие бота помечаются в users.is_blocked_bot и в следующие
  рассылки не попадают.
• Прогресс обновляется в сообщении у администратора, рассылку можно
  остановить. Если бот перезапустился посреди рассылки — она помечается
  как прерванная (interrupted), а не висит «в процессе» вечно.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks import AdminCB
from bot.keyboards.common import btn, kb
from config import emoji as E
from config.settings import Settings
from database.database import Database
from database.models import Broadcast, BroadcastResult, utcnow
from database.repositories import Repo
from utils.text import progress_bar

log = logging.getLogger(__name__)

PROGRESS_EVERY = 3.0  # сек между обновлениями прогресса
RESULTS_BATCH = 200
MAX_RETRIES = 5


def buttons_markup(rows: list[list[dict[str, str]]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in rows]
    )


def report_text(b: Broadcast, title: str) -> str:
    done = b.sent + b.failed + b.blocked
    return (
        f"{E.BROADCAST_EMOJI} <b>{title} #{b.id}</b>\n\n"
        f"{progress_bar(done, b.total)} {done}/{b.total}\n\n"
        f"Получателей: <b>{b.total}</b>\n"
        f"✅ Успешно: <b>{b.sent}</b>\n"
        f"⚠️ Ошибок: <b>{b.failed}</b>\n"
        f"🚫 Заблокировали бота: <b>{b.blocked}</b>"
    )


class BroadcastService:
    def __init__(self, bot: Bot, db: Database, settings: Settings) -> None:
        self.bot = bot
        self.db = db
        self.delay = 1.0 / settings.broadcast_rate
        self._task: asyncio.Task | None = None
        self._cancel = asyncio.Event()
        self.current_id: int | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def recover(self) -> None:
        """После перезапуска: незавершённые рассылки → interrupted."""
        async with self.db.session() as session:
            repo = Repo(session)
            for b in await repo.broadcasts.running():
                b.status = "interrupted"
                b.finished_at = utcnow()
            await repo.commit()

    def start(self, broadcast_id: int, admin_chat_id: int, status_message_id: int) -> bool:
        if self.running:
            return False
        self._cancel.clear()
        self.current_id = broadcast_id
        self._task = asyncio.create_task(self._run(broadcast_id, admin_chat_id, status_message_id))
        return True

    def cancel(self) -> None:
        self._cancel.set()

    async def shutdown(self) -> None:
        if self.running:
            self._cancel.set()
            try:
                await asyncio.wait_for(self._task, timeout=10)  # type: ignore[arg-type]
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()  # type: ignore[union-attr]

    async def _send_one(self, user_id: int, b: Broadcast, markup: InlineKeyboardMarkup | None) -> str:
        for _ in range(MAX_RETRIES):
            try:
                await self.bot.copy_message(user_id, b.source_chat_id, b.source_message_id, reply_markup=markup)
                return "sent"
            except TelegramRetryAfter as error:
                log.warning("Рассылка #%s: flood control, ждём %s c", b.id, error.retry_after)
                await asyncio.sleep(error.retry_after + 1)
            except TelegramForbiddenError:
                return "blocked"
            except TelegramBadRequest as error:
                low = error.message.lower()
                if "chat not found" in low or "user is deactivated" in low:
                    return "blocked"
                return f"failed:{error.message[:200]}"
            except TelegramAPIError as error:
                return f"failed:{str(error)[:200]}"
        return "failed:retry limit"

    async def _progress(self, b: Broadcast, chat_id: int, message_id: int, final: bool = False) -> None:
        title = {"done": "Рассылка завершена", "cancelled": "Рассылка остановлена"}.get(b.status, "Идёт рассылка")
        markup = None if final else kb(
            btn("Остановить", AdminCB(section="bc", action="stop", id=b.id), icon=E.CROSS_EMOJI, style="danger")
        )
        try:
            await self.bot.edit_message_text(report_text(b, title), chat_id=chat_id, message_id=message_id,
                                             reply_markup=markup)
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after)
        except TelegramAPIError:
            pass

    async def _run(self, broadcast_id: int, chat_id: int, message_id: int) -> None:
        try:
            async with self.db.session() as session:
                repo = Repo(session)
                b = await repo.broadcasts.get(broadcast_id)
                if b is None:
                    return
                user_ids = await repo.users.broadcast_ids()
                b.total = len(user_ids)
                b.status = "running"
                b.started_at = utcnow()
                await repo.commit()
                markup = buttons_markup(b.buttons)
                log.info("Рассылка #%s: старт, получателей %s", b.id, b.total)

                results: list[BroadcastResult] = []
                last_progress = 0.0
                for user_id in user_ids:
                    if self._cancel.is_set():
                        b.status = "cancelled"
                        break
                    started = time.monotonic()
                    outcome = await self._send_one(user_id, b, markup)
                    status, _, error = outcome.partition(":")
                    if status == "sent":
                        b.sent += 1
                    elif status == "blocked":
                        b.blocked += 1
                        await repo.users.set_blocked_bot(user_id, True)
                    else:
                        b.failed += 1
                    results.append(BroadcastResult(broadcast_id=b.id, user_id=user_id, status=status,
                                                   error=error or None))
                    if len(results) >= RESULTS_BATCH:
                        await repo.broadcasts.add_results(results)
                        await repo.commit()
                        results = []
                    if time.monotonic() - last_progress > PROGRESS_EVERY:
                        last_progress = time.monotonic()
                        await self._progress(b, chat_id, message_id)
                    spent = time.monotonic() - started
                    if spent < self.delay:
                        await asyncio.sleep(self.delay - spent)
                else:
                    b.status = "done"

                if results:
                    await repo.broadcasts.add_results(results)
                b.finished_at = utcnow()
                await repo.commit()
                log.info("Рассылка #%s: %s — ok %s, ошибок %s, заблокировали %s",
                         b.id, b.status, b.sent, b.failed, b.blocked)
                await self._progress(b, chat_id, message_id, final=True)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Рассылка #%s упала", broadcast_id)
            try:
                await self.bot.send_message(chat_id, f"{E.WARNING_EMOJI} Рассылка #{broadcast_id} прервана "
                                                     "из-за ошибки — подробности в логах.")
            except TelegramAPIError:
                pass
        finally:
            self.current_id = None
