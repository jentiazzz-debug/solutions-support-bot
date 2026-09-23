"""/start, главное меню, «О нас», проекты, портфолио, реклама."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.callbacks import MenuCB, ProjectCB
from bot.handlers.support import show_support, show_user_ticket
from bot.keyboards.main import about_kb, ads_kb, main_menu_kb, portfolio_kb, project_kb
from bot.services.content import about_screen, get_text, project_card
from bot.services.render import safe_answer, show
from database.repositories import Repo
from support.deeplink import parse_start_payload

log = logging.getLogger(__name__)
router = Router(name="menu")


async def show_main(event: Message | CallbackQuery, repo: Repo, is_admin: bool) -> None:
    text = await get_text(repo, "welcome_text")
    photo = await repo.settings.get("welcome_photo")
    buttons = await repo.menu.all()
    await show(event, text, main_menu_kb(buttons, is_admin), photo=photo)


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, repo: Repo, is_admin: bool, user
) -> None:
    await state.clear()
    parsed = parse_start_payload(command.args)
    if parsed and parsed[0] == "ticket":
        ticket = await repo.tickets.get(parsed[1])
        if ticket is not None and ticket.user_id == user.id:
            await show_user_ticket(message, repo, ticket)
            return
    sticker = await repo.settings.get("welcome_sticker")
    if sticker:
        try:
            await message.answer_sticker(sticker)
        except TelegramBadRequest as error:
            log.warning("Стикер приветствия не отправился: %s", error.message)
    await show_main(message, repo, is_admin)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, repo: Repo, is_admin: bool) -> None:
    await state.clear()
    await show_main(message, repo, is_admin)


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext, repo: Repo, user) -> None:
    await state.clear()
    await show_support(message, repo, user.id)


@router.callback_query(MenuCB.filter(F.section == "main"))
async def cb_main(callback: CallbackQuery, state: FSMContext, repo: Repo, is_admin: bool) -> None:
    await state.clear()
    await show_main(callback, repo, is_admin)
    await safe_answer(callback)


@router.callback_query(MenuCB.filter(F.section == "about"))
async def cb_about(callback: CallbackQuery, repo: Repo) -> None:
    text, projects = await about_screen(repo)
    await show(callback, text, about_kb(projects))
    await safe_answer(callback)


@router.callback_query(ProjectCB.filter())
async def cb_project(callback: CallbackQuery, callback_data: ProjectCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is None or not project.is_visible:
        await safe_answer(callback, "Проект не найден", alert=True)
        return
    await show(callback, project_card(project), project_kb(project), photo=project.image_file_id)
    await safe_answer(callback)


@router.callback_query(MenuCB.filter(F.section == "portfolio"))
async def cb_portfolio(callback: CallbackQuery, repo: Repo) -> None:
    text = await get_text(repo, "portfolio_text")
    links = await repo.links.all(only_enabled=True)
    await show(callback, text, portfolio_kb(links))
    await safe_answer(callback)


@router.callback_query(MenuCB.filter(F.section == "ads"))
async def cb_ads(callback: CallbackQuery, repo: Repo) -> None:
    text = await get_text(repo, "ads_text")
    username = (await repo.settings.get("support_username") or "").lstrip("@")
    manager_url = f"https://t.me/{username}" if username else None
    await show(callback, text, ads_kb(manager_url))
    await safe_answer(callback)


@router.callback_query(MenuCB.filter(F.section == "support"))
async def cb_support(callback: CallbackQuery, state: FSMContext, repo: Repo, user) -> None:
    await state.clear()
    await show_support(callback, repo, user.id)
    await safe_answer(callback)
