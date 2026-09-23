"""Поддержка со стороны пользователя: создание тикета, мои обращения, переписка."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReactionTypeEmoji

from bot.callbacks import MenuCB, SupportCB
from bot.keyboards.common import btn, kb
from bot.keyboards.main import (
    cancel_kb,
    categories_kb,
    choose_ticket_kb,
    confirm_close_kb,
    my_tickets_kb,
    support_kb,
    user_ticket_kb,
)
from bot.services.content import get_text
from bot.services.locks import user_lock
from bot.services.render import safe_answer, show
from bot.states import TicketStates
from config import emoji as E
from database.models import Ticket, TicketCategory, User
from database.repositories import Repo
from support.deeplink import support_dm_link
from support.ticket_service import TicketError, TicketService
from utils.text import esc, fmt_dt

log = logging.getLogger(__name__)
router = Router(name="support")

STATUS_TITLES = {
    "OPEN": "🟢 Открыт",
    "IN_PROGRESS": "🟡 В работе",
    "CLOSED": "⚪ Закрыт",
    "BANNED": "⛔ Заблокирован",
}


async def show_support(event: Message | CallbackQuery, repo: Repo, user_id: int) -> None:
    text = await get_text(repo, "support_text")
    active = await repo.tickets.count_active_for_user(user_id)
    await show(event, text, support_kb(active))


async def show_user_ticket(event: Message | CallbackQuery, repo: Repo, ticket: Ticket) -> None:
    from config import get_settings

    tz = get_settings().tz
    count = await repo.tickets.count_messages(ticket.id)
    lines = [
        f"{E.TICKET_EMOJI} <b>Обращение {ticket.number}</b>\n",
        f"{E.CATEGORY_EMOJI} Категория: {esc(ticket.category_title)}",
        f"Статус: {STATUS_TITLES.get(ticket.status, ticket.status)}",
        f"{E.TIME_EMOJI} Создано: {fmt_dt(ticket.created_at, tz)}",
        f"{E.MESSAGE_EMOJI} Сообщений: {count}",
    ]
    if ticket.closed_at:
        lines.append(f"Закрыто: {fmt_dt(ticket.closed_at, tz)}")
        if ticket.close_reason:
            lines.append(f"Причина: {esc(ticket.close_reason)}")
    username = await repo.settings.get("support_username") or ""
    await show(event, "\n".join(lines), user_ticket_kb(ticket, support_dm_link(username, ticket.id)))


async def _owned_ticket(repo: Repo, ticket_id: int, user_id: int) -> Ticket | None:
    ticket = await repo.tickets.get(ticket_id)
    return ticket if ticket is not None and ticket.user_id == user_id else None


# ------------------------------------------------------------------ создание


@router.callback_query(SupportCB.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, state: FSMContext, repo: Repo, tickets: TicketService,
                 user: User) -> None:
    error = await tickets.creation_error(user.id)
    if error:
        await show(callback, error, kb(
            btn("Мои обращения", SupportCB(action="my"), icon=E.MY_TICKETS_EMOJI),
            btn("Назад", MenuCB(section="support"), icon=E.BACK_EMOJI),
        ))
        await safe_answer(callback)
        return
    categories = await repo.categories.all(only_enabled=True)
    await state.set_state(TicketStates.choosing_category)
    await show(callback, f"{E.CATEGORY_EMOJI} <b>Выберите тему обращения:</b>", categories_kb(categories))
    await safe_answer(callback)


async def _choose_category(
    callback: CallbackQuery, state: FSMContext, tickets: TicketService, user: User,
    category: TicketCategory,
) -> None:
    error = await tickets.creation_error(user.id)
    if error:
        await show(callback, error, kb(btn("Назад", MenuCB(section="support"), icon=E.BACK_EMOJI)))
        return
    await state.set_state(TicketStates.waiting_message)
    await state.update_data(category_id=category.id)
    await show(
        callback,
        f"{E.CATEGORY_EMOJI} Тема: <b>{esc(category.label)}</b>\n\n"
        f"{E.MESSAGE_EMOJI} Опишите вопрос одним сообщением.\n"
        "Можно отправить текст, фото, видео, GIF, документ, стикер или голосовое.",
        cancel_kb(),
    )


@router.callback_query(SupportCB.filter(F.action == "cat"))
async def cb_category(callback: CallbackQuery, callback_data: SupportCB, state: FSMContext, repo: Repo,
                      tickets: TicketService, user: User) -> None:
    category = await repo.categories.get(callback_data.id)
    if category is None or not category.is_enabled:
        await safe_answer(callback, "Категория недоступна", alert=True)
        return
    await _choose_category(callback, state, tickets, user, category)
    await safe_answer(callback)


@router.callback_query(SupportCB.filter(F.action == "ads_order"))
async def cb_ads_order(callback: CallbackQuery, state: FSMContext, repo: Repo, tickets: TicketService,
                       user: User) -> None:
    categories = await repo.categories.all(only_enabled=True)
    category = next((c for c in categories if "реклам" in c.title.lower()), None)
    if category is None:
        await cb_new(callback, state, repo, tickets, user)
        return
    await _choose_category(callback, state, tickets, user, category)
    await safe_answer(callback)


@router.message(TicketStates.waiting_message)
async def first_message(message: Message, state: FSMContext, repo: Repo, tickets: TicketService,
                        user: User) -> None:
    async with user_lock(user.id):
        if await state.get_state() != TicketStates.waiting_message.state:
            # Альбом: первое фото уже создало тикет — остальные идут в него.
            await route_user_message(message, repo, tickets, user, state)
            return
        data = await state.get_data()
        category = await repo.categories.get(int(data.get("category_id") or 0))
        if category is None:
            await state.clear()
            await message.answer("Категория больше недоступна. Начните заново.",
                                 reply_markup=kb(btn("Поддержка", MenuCB(section="support"))))
            return
        try:
            ticket = await tickets.create(user, category, message)
        except TicketError as error:
            await state.clear()
            await message.answer(str(error), reply_markup=kb(
                btn("Мои обращения", SupportCB(action="my"), icon=E.MY_TICKETS_EMOJI)))
            return
        await state.clear()

    username = await repo.settings.get("support_username") or ""
    dm_link = support_dm_link(username, ticket.id)
    await message.answer(
        f"{E.CLOSE_EMOJI} <b>Обращение {ticket.number} создано</b>\n\n"
        f"Тема: {esc(ticket.category_title)}\n"
        "Мы ответим прямо в этот чат. Можете дописать детали — просто отправьте "
        "ещё сообщения, они попадут в это обращение.",
        reply_markup=kb(
            btn("Мои обращения", SupportCB(action="my"), icon=E.MY_TICKETS_EMOJI),
            btn("Написать в ЛС поддержки", url=dm_link, icon=E.LINK_EMOJI) if dm_link else None,
            btn("Главное меню", MenuCB(section="main"), icon=E.HOME_EMOJI),
        ),
    )


@router.message(TicketStates.choosing_category)
async def waiting_category(message: Message, repo: Repo) -> None:
    categories = await repo.categories.all(only_enabled=True)
    await message.answer(f"{E.CATEGORY_EMOJI} Сначала выберите тему обращения:",
                         reply_markup=categories_kb(categories))


# ------------------------------------------------------------------ мои обращения


@router.callback_query(SupportCB.filter(F.action == "my"))
async def cb_my(callback: CallbackQuery, state: FSMContext, repo: Repo, user: User) -> None:
    await state.clear()
    active = await repo.tickets.active_for_user(user.id)
    if active:
        text = f"{E.MY_TICKETS_EMOJI} <b>Ваши активные обращения</b>\n\n" + "\n".join(
            f"{t.number} · {esc(t.category_title)} — {STATUS_TITLES.get(t.status, t.status)}"
            for t in active
        )
    else:
        text = f"{E.MY_TICKETS_EMOJI} У вас нет активных обращений."
    await show(callback, text, my_tickets_kb(active))
    await safe_answer(callback)


@router.callback_query(SupportCB.filter(F.action == "open"))
async def cb_open(callback: CallbackQuery, callback_data: SupportCB, repo: Repo, user: User) -> None:
    ticket = await _owned_ticket(repo, callback_data.id, user.id)
    if ticket is None:
        await safe_answer(callback, "Обращение не найдено", alert=True)
        return
    await show_user_ticket(callback, repo, ticket)
    await safe_answer(callback)


@router.callback_query(SupportCB.filter(F.action == "write"))
async def cb_write(callback: CallbackQuery, callback_data: SupportCB, state: FSMContext, repo: Repo,
                   user: User) -> None:
    ticket = await _owned_ticket(repo, callback_data.id, user.id)
    if ticket is None or not ticket.is_active:
        await safe_answer(callback, "Обращение закрыто", alert=True)
        return
    await state.clear()
    await repo.users.set_active_ticket(user.id, ticket.id)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"{E.REPLY_EMOJI} Напишите сообщение — оно уйдёт в обращение <b>{ticket.number}</b>."
        )
    await safe_answer(callback)


@router.callback_query(SupportCB.filter(F.action == "close"))
async def cb_close(callback: CallbackQuery, callback_data: SupportCB, repo: Repo, user: User) -> None:
    ticket = await _owned_ticket(repo, callback_data.id, user.id)
    if ticket is None or not ticket.is_active:
        await safe_answer(callback, "Обращение уже закрыто", alert=True)
        return
    await show(callback, f"Закрыть обращение <b>{ticket.number}</b>?", confirm_close_kb(ticket))
    await safe_answer(callback)


@router.callback_query(SupportCB.filter(F.action == "close_yes"))
async def cb_close_yes(callback: CallbackQuery, callback_data: SupportCB, repo: Repo,
                       tickets: TicketService, user: User) -> None:
    ticket = await _owned_ticket(repo, callback_data.id, user.id)
    if ticket is None:
        await safe_answer(callback, "Обращение не найдено", alert=True)
        return
    try:
        await tickets.close(ticket, closed_by=user.id, by_user=True)
    except TicketError as error:
        await safe_answer(callback, str(error), alert=True)
        return
    await show(callback, f"{E.CLOSE_EMOJI} Обращение <b>{ticket.number}</b> закрыто. Спасибо!", kb(
        btn("Новое обращение", SupportCB(action="new"), icon=E.NEW_TICKET_EMOJI, style="primary"),
        btn("Главное меню", MenuCB(section="main"), icon=E.HOME_EMOJI),
    ))
    await safe_answer(callback)


# ------------------------------------------------------------------ переписка


async def _react(bot: Bot, message: Message) -> None:
    try:
        await bot.set_message_reaction(message.chat.id, message.message_id,
                                       [ReactionTypeEmoji(emoji="👌")])
    except TelegramBadRequest:
        pass


async def route_user_message(message: Message, repo: Repo, tickets: TicketService, user: User,
                             state: FSMContext | None = None) -> None:
    """Куда отправить сообщение пользователя без активного сценария."""
    if await repo.bans.is_banned(user.id):
        await message.answer(f"{E.BAN_EMOJI} Доступ к поддержке для вас ограничен.")
        return

    ticket: Ticket | None = None
    if message.reply_to_message is not None:
        linked = await repo.tickets.by_link(message.chat.id, message.reply_to_message.message_id)
        if linked is not None and linked.user_id == user.id:
            ticket = linked
    if ticket is None and user.active_ticket_id:
        candidate = await repo.tickets.get(user.active_ticket_id)
        if candidate is not None and candidate.user_id == user.id and candidate.is_active:
            ticket = candidate
    if ticket is None:
        active = await repo.tickets.active_for_user(user.id)
        if len(active) == 1:
            ticket = active[0]
        elif len(active) > 1:
            await message.answer(
                f"{E.TICKET_EMOJI} У вас несколько открытых обращений. Выберите, куда написать, "
                "и отправьте сообщение ещё раз:",
                reply_markup=choose_ticket_kb(active),
            )
            return
    if ticket is None:
        await message.answer(
            f"{E.SUPPORT_EMOJI} Чтобы написать в поддержку, создайте обращение.",
            reply_markup=kb(
                btn("Создать обращение", SupportCB(action="new"), icon=E.NEW_TICKET_EMOJI, style="primary"),
                btn("Главное меню", MenuCB(section="main"), icon=E.HOME_EMOJI),
            ),
        )
        return
    if not ticket.is_active:
        await message.answer(f"Обращение {ticket.number} закрыто. Создайте новое.",
                             reply_markup=kb(btn("Новое обращение", SupportCB(action="new"))))
        return
    try:
        await tickets.user_message(ticket, message)
    except TicketError as error:
        await message.answer(str(error))
        return
    await _react(message.bot, message)  # type: ignore[arg-type]
