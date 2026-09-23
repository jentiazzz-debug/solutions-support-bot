"""Вход в админ-панель."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import panel_kb
from admin.services.ticket_view import ticket_card
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.services.render import safe_answer, show
from config import emoji as E
from database.models import TicketStatus
from database.repositories import Repo
from support.deeplink import parse_start_payload

router = Router(name="admin_panel")


async def show_panel(event: Message | CallbackQuery, repo: Repo, is_owner: bool) -> None:
    by_status = await repo.tickets.count_by_status()
    open_count = by_status.get(TicketStatus.OPEN.value, 0)
    in_progress = by_status.get(TicketStatus.IN_PROGRESS.value, 0)
    users = await repo.users.count()
    text = (
        f"{E.ADMIN_EMOJI} <b>Админ-панель</b>\n\n"
        f"{E.TICKET_EMOJI} Открытых тикетов: <b>{open_count}</b> · в работе: <b>{in_progress}</b>\n"
        f"{E.USERS_EMOJI} Пользователей: <b>{users}</b>"
    )
    await show(event, text, panel_kb(is_owner, open_count + in_progress))


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, repo: Repo, is_owner: bool) -> None:
    await state.clear()
    await show_panel(message, repo, is_owner)


@router.message(CommandStart(deep_link=True), F.text.regexp(r"^/start adm\d+$"))
async def start_admin_link(message: Message, command: CommandObject, state: FSMContext, repo: Repo,
                           ctx: AppContext) -> None:
    await state.clear()
    parsed = parse_start_payload(command.args)
    ticket = await repo.tickets.get(parsed[1]) if parsed else None
    if ticket is None:
        await message.answer("Тикет не найден.")
        return
    text, markup = await ticket_card(repo, ticket, ctx.settings.tz)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminCB.filter(F.section == "home"))
async def cb_home(callback: CallbackQuery, state: FSMContext, repo: Repo, is_owner: bool) -> None:
    await state.clear()
    await show_panel(callback, repo, is_owner)
    await safe_answer(callback)
