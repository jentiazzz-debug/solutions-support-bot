"""Последний роутер: сообщения без сценария и устаревшие кнопки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.menu import show_main
from bot.handlers.support import route_user_message
from bot.services.render import safe_answer
from database.models import User
from database.repositories import Repo
from support.ticket_service import TicketService

router = Router(name="fallback")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await safe_answer(callback)


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message, state: FSMContext, repo: Repo, is_admin: bool) -> None:
    await state.clear()
    await show_main(message, repo, is_admin)


@router.message()
async def any_message(message: Message, state: FSMContext, repo: Repo, tickets: TicketService,
                      user: User) -> None:
    await route_user_message(message, repo, tickets, user, state)


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await safe_answer(callback, "Кнопка устарела — откройте меню заново: /start", alert=True)
