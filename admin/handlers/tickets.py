"""Работа администратора с тикетами."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReactionTypeEmoji

from admin.keyboards.panel import back_to_panel
from admin.services.ticket_view import STATUS_TITLES, history_page, ticket_card
from bot.callbacks import AdminCB, TicketCB
from bot.context import AppContext
from bot.keyboards.common import btn, kb, pager
from bot.keyboards.tickets import admin_reply_mode_kb
from bot.services.render import safe_answer, show
from bot.states import AdminTicketStates
from config import emoji as E
from database.models import Ticket
from database.repositories import Repo, TicketFilter
from support.deeplink import admin_ticket_link, bot_ticket_link, support_dm_link, support_prefill_text
from support.message_service import CONTENT_LABELS, send_stored
from support.ticket_service import TicketError, TicketService
from utils.text import esc, truncate

log = logging.getLogger(__name__)
router = Router(name="admin_tickets")

PAGE = 8
FILTERS: list[tuple[str, str]] = [
    ("all", "Все"),
    ("OPEN", "Открытые"),
    ("IN_PROGRESS", "В работе"),
    ("CLOSED", "Закрытые"),
    ("BANNED", "Заблок."),
]
STATUS_DOT = {"OPEN": "🟢", "IN_PROGRESS": "🟡", "CLOSED": "⚪", "BANNED": "⛔"}


# ------------------------------------------------------------------ список


def _filter_from(action: str, data: dict) -> TicketFilter:
    if action == "found":
        return TicketFilter(**data.get("ticket_search", {}))
    if action in {"OPEN", "IN_PROGRESS", "CLOSED", "BANNED"}:
        return TicketFilter(status=action)
    return TicketFilter()


def _describe(flt: TicketFilter) -> str:
    parts = []
    if flt.ticket_id:
        parts.append(f"номер #{flt.ticket_id}")
    if flt.user_id:
        parts.append(f"ID {flt.user_id}")
    if flt.username:
        parts.append(f"@{esc(flt.username)}")
    if flt.category:
        parts.append(f"категория «{esc(flt.category)}»")
    return ", ".join(parts)


async def show_list(event: Message | CallbackQuery, repo: Repo, state: FSMContext, action: str = "all",
                    page: int = 0) -> None:
    data = await state.get_data()
    flt = _filter_from(action, data)
    items, total = await repo.tickets.page(flt, offset=page * PAGE, limit=PAGE)
    counts = await repo.tickets.count_by_status()

    header = f"{E.TICKET_EMOJI} <b>Тикеты</b>\n"
    header += " · ".join(f"{STATUS_DOT[s]} {counts.get(s, 0)}" for s in STATUS_DOT)
    if action == "found":
        header += f"\n\n{E.SEARCH_EMOJI} Поиск: {_describe(flt)} — найдено {total}"
    elif not total:
        header += "\n\nТикетов нет."

    filter_row = [
        btn(("• " if action == code else "") + title, AdminCB(section="tickets", action=code))
        for code, title in FILTERS
    ]
    ticket_buttons = [
        btn(
            truncate(f"{STATUS_DOT.get(t.status, '')} {t.number} · {t.user_mention} · {t.category_title}", 60),
            TicketCB(action="open", id=t.id, page=1),
        )
        for t in items
    ]
    nav = pager(lambda p: AdminCB(section="tickets", action=action, page=p), page, total, PAGE)
    markup = kb(
        filter_row[:3],
        filter_row[3:],
        *ticket_buttons,
        nav,
        [btn("Поиск", AdminCB(section="tickets", action="search"), icon=E.SEARCH_EMOJI), back_to_panel()],
    )
    await show(event, header, markup)


@router.callback_query(AdminCB.filter((F.section == "tickets") & (F.action != "search")))
async def cb_list(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await state.set_state(None)
    await show_list(callback, repo, state, callback_data.action or "all", callback_data.page)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == "tickets") & (F.action == "search")))
async def cb_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminTicketStates.search)
    await show(
        callback,
        f"{E.SEARCH_EMOJI} <b>Поиск тикетов</b>\n\n"
        "Отправьте:\n"
        "• <code>#1042</code> — номер тикета\n"
        "• <code>123456789</code> — Telegram ID пользователя\n"
        "• <code>@username</code> — username\n"
        "• любой текст — название категории",
        kb(btn("Отмена", AdminCB(section="tickets"), icon=E.CROSS_EMOJI)),
    )
    await safe_answer(callback)


@router.message(AdminTicketStates.search, F.text)
async def do_search(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    query = (message.text or "").strip()
    flt: dict = {}
    if query.startswith("#") and query[1:].isdigit():
        flt["ticket_id"] = int(query[1:])
    elif query.lstrip("-").isdigit():
        ticket = await repo.tickets.get(int(query)) if len(query) <= 9 else None
        if ticket is not None:
            await state.set_state(None)
            text, markup = await ticket_card(repo, ticket, ctx.settings.tz)
            await message.answer(text, reply_markup=markup)
            return
        flt["user_id"] = int(query)
    elif query.startswith("@"):
        flt["username"] = query.lstrip("@")
    else:
        flt["category"] = query[:64]
    await state.set_state(None)
    await state.update_data(ticket_search=flt)
    await show_list(message, repo, state, "found")


# ------------------------------------------------------------------ карточка


async def _ticket(callback: CallbackQuery, repo: Repo, ticket_id: int) -> Ticket | None:
    ticket = await repo.tickets.get(ticket_id)
    if ticket is None:
        await safe_answer(callback, "Тикет не найден", alert=True)
    return ticket


async def refresh_card(event: Message | CallbackQuery, repo: Repo, ticket: Ticket, ctx: AppContext) -> None:
    text, markup = await ticket_card(repo, ticket, ctx.settings.tz)
    await show(event, text, markup)


@router.callback_query(TicketCB.filter(F.action == "open"))
async def cb_open(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, ctx: AppContext) -> None:
    """page=1 — открыть на месте (из списка/истории), page=0 — новым сообщением
    (из уведомления или копии сообщения пользователя — их не затираем)."""
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    text, markup = await ticket_card(repo, ticket, ctx.settings.tz)
    if callback_data.page == 1 or not isinstance(callback.message, Message):
        await show(callback, text, markup)
    else:
        await callback.message.answer(text, reply_markup=markup)
    await safe_answer(callback)


@router.callback_query(TicketCB.filter(F.action == "take"))
async def cb_take(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, tickets: TicketService,
                  ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    await tickets.take(ticket, callback.from_user.id)
    await refresh_card(callback, repo, ticket, ctx)
    await safe_answer(callback, f"Тикет {ticket.number} взят в работу")


# ------------------------------------------------------------------ ответы


@router.callback_query(TicketCB.filter(F.action == "reply"))
async def cb_reply(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, state: FSMContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    if not ticket.is_active:
        await safe_answer(callback, "Тикет закрыт — ответить нельзя", alert=True)
        return
    await state.set_state(AdminTicketStates.replying)
    await state.update_data(reply_ticket=ticket.id)
    await callback.message.answer(  # type: ignore[union-attr]
        f"{E.REPLY_EMOJI} <b>Режим ответа · {ticket.number}</b> ({esc(ticket.user_mention)})\n\n"
        "Отправляйте сообщения — текст, фото, GIF, видео, документы, стикеры, голосовые. "
        "Всё уйдёт пользователю от имени бота.\n"
        "/quick — быстрые ответы · /cancel — выйти из режима",
        reply_markup=admin_reply_mode_kb(ticket),
    )
    await safe_answer(callback)


@router.callback_query(TicketCB.filter(F.action == "stop"))
async def cb_stop(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(callback, "Режим ответа завершён.", kb(back_to_panel()))
    await safe_answer(callback)


@router.message(AdminTicketStates.replying, Command("cancel"))
async def cmd_cancel_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Режим ответа завершён.", reply_markup=kb(back_to_panel()))


@router.message(AdminTicketStates.replying, Command("quick"))
async def cmd_quick_in_reply(message: Message, state: FSMContext, repo: Repo) -> None:
    ticket_id = (await state.get_data()).get("reply_ticket")
    ticket = await repo.tickets.get(int(ticket_id or 0))
    if ticket is None:
        await state.clear()
        await message.answer("Тикет не найден.")
        return
    await message.answer(*await _quick_list(repo, ticket))


async def _react(bot: Bot, message: Message) -> None:
    try:
        await bot.set_message_reaction(message.chat.id, message.message_id, [ReactionTypeEmoji(emoji="👌")])
    except TelegramBadRequest:
        await message.answer("✅ Доставлено")


async def _deliver(message: Message, ticket: Ticket, tickets: TicketService) -> None:
    try:
        await tickets.admin_message(ticket, message.from_user.id, message)  # type: ignore[union-attr]
    except TicketError as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    except TelegramAPIError as error:
        log.warning("Ответ в %s не доставлен: %s", ticket.number, error)
        await message.answer(f"{E.WARNING_EMOJI} Telegram не принял сообщение: {esc(error.message)}")
        return
    await _react(message.bot, message)  # type: ignore[arg-type]


@router.message(
    StateFilter(None, AdminTicketStates.replying),
    F.reply_to_message,
    ~F.text.startswith("/"),
)
async def reply_to_linked(message: Message, state: FSMContext, repo: Repo, tickets: TicketService) -> None:
    """Админ ответил (reply) на сообщение пользователя — отправляем в нужный тикет."""
    ticket = await repo.tickets.by_link(message.chat.id, message.reply_to_message.message_id)  # type: ignore[union-attr]
    if ticket is None:
        if await state.get_state() == AdminTicketStates.replying.state:
            await in_reply_mode(message, state, repo, tickets)
        else:
            await message.answer("Это сообщение не относится к тикету. Откройте тикет: /admin")
        return
    if not ticket.is_active:
        await message.answer(f"Тикет {ticket.number} закрыт — ответ не отправлен.")
        return
    await _deliver(message, ticket, tickets)


@router.message(AdminTicketStates.replying, ~F.text.startswith("/"))
async def in_reply_mode(message: Message, state: FSMContext, repo: Repo, tickets: TicketService) -> None:
    ticket_id = (await state.get_data()).get("reply_ticket")
    ticket = await repo.tickets.get(int(ticket_id or 0))
    if ticket is None or not ticket.is_active:
        await state.clear()
        await message.answer("Тикет закрыт или не найден — режим ответа завершён.")
        return
    await _deliver(message, ticket, tickets)


# ------------------------------------------------------------------ быстрые ответы


async def _quick_list(repo: Repo, ticket: Ticket):
    replies = await repo.quick_replies.all()
    if not replies:
        return (
            f"{E.QUICK_EMOJI} Быстрых ответов пока нет.",
            kb(btn("Создать", AdminCB(section="qr", action="new"), icon=E.PLUS_EMOJI),
               btn("К тикету", TicketCB(action="open", id=ticket.id, page=1), icon=E.BACK_EMOJI)),
        )
    buttons = [
        btn(truncate(q.title, 40), TicketCB(action="qsend", id=ticket.id, extra=q.id)) for q in replies
    ]
    return (
        f"{E.QUICK_EMOJI} <b>Быстрые ответы · {ticket.number}</b>\nВыберите ответ — он сразу уйдёт пользователю.",
        kb(*buttons, btn("К тикету", TicketCB(action="open", id=ticket.id, page=1), icon=E.BACK_EMOJI)),
    )


@router.callback_query(TicketCB.filter(F.action == "quick"))
async def cb_quick(callback: CallbackQuery, callback_data: TicketCB, repo: Repo) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    text, markup = await _quick_list(repo, ticket)
    await callback.message.answer(text, reply_markup=markup)  # type: ignore[union-attr]
    await safe_answer(callback)


@router.callback_query(TicketCB.filter(F.action == "qsend"))
async def cb_quick_send(callback: CallbackQuery, callback_data: TicketCB, repo: Repo,
                        tickets: TicketService) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    quick = await repo.quick_replies.get(callback_data.extra)
    if ticket is None:
        return
    if quick is None:
        await safe_answer(callback, "Быстрый ответ удалён", alert=True)
        return
    if not ticket.is_active:
        await safe_answer(callback, "Тикет закрыт", alert=True)
        return
    try:
        await tickets.send_quick_reply(ticket, callback.from_user.id, quick)
    except (TicketError, TelegramAPIError) as error:
        await safe_answer(callback, str(error)[:190], alert=True)
        return
    await safe_answer(callback, f"«{quick.title}» отправлен в {ticket.number}")


# ------------------------------------------------------------------ закрытие


@router.callback_query(TicketCB.filter(F.action == "close"))
async def cb_close(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, tickets: TicketService,
                   state: FSMContext, ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    try:
        await tickets.close(ticket, callback.from_user.id)
    except TicketError as error:
        await safe_answer(callback, str(error), alert=True)
        return
    data = await state.get_data()
    if data.get("reply_ticket") == ticket.id:
        await state.clear()
    await refresh_card(callback, repo, ticket, ctx)
    await safe_answer(callback, f"Тикет {ticket.number} закрыт")


@router.callback_query(TicketCB.filter(F.action == "closer"))
async def cb_close_reason(callback: CallbackQuery, callback_data: TicketCB, repo: Repo,
                          state: FSMContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    await state.set_state(AdminTicketStates.close_reason)
    await state.update_data(close_ticket=ticket.id)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Причина закрытия {ticket.number}? Её увидит пользователь.",
        reply_markup=kb(btn("Отмена", TicketCB(action="open", id=ticket.id, page=1), icon=E.CROSS_EMOJI)),
    )
    await safe_answer(callback)


@router.message(AdminTicketStates.close_reason, F.text)
async def do_close_reason(message: Message, state: FSMContext, repo: Repo, tickets: TicketService,
                          ctx: AppContext) -> None:
    data = await state.get_data()
    ticket = await repo.tickets.get(int(data.get("close_ticket") or 0))
    await state.clear()
    if ticket is None:
        await message.answer("Тикет не найден.")
        return
    try:
        await tickets.close(ticket, message.from_user.id, reason=(message.text or "")[:500])  # type: ignore[union-attr]
    except TicketError as error:
        await message.answer(str(error))
        return
    await refresh_card(message, repo, ticket, ctx)


# ------------------------------------------------------------------ блокировка


@router.callback_query(TicketCB.filter(F.action == "ban"))
async def cb_ban(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, state: FSMContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    await state.set_state(AdminTicketStates.ban_reason)
    await state.update_data(ban_ticket=ticket.id)
    await callback.message.answer(  # type: ignore[union-attr]
        f"{E.BAN_EMOJI} Заблокировать <b>{esc(ticket.user_mention)}</b> в поддержке?\n"
        "Все активные обращения будут закрыты.\n\n"
        "Отправьте причину или нажмите «Без причины».",
        reply_markup=kb(
            btn("Без причины", TicketCB(action="banok", id=ticket.id), style="danger"),
            btn("Отмена", TicketCB(action="open", id=ticket.id, page=1), icon=E.CROSS_EMOJI),
        ),
    )
    await safe_answer(callback)


async def _do_ban(event: Message | CallbackQuery, ticket: Ticket, reason: str | None, admin_id: int,
                  repo: Repo, tickets: TicketService, ctx: AppContext) -> None:
    try:
        closed = await tickets.ban(ticket.user_id, admin_id, reason)
    except TicketError as error:
        if isinstance(event, CallbackQuery):
            await safe_answer(event, str(error), alert=True)
        else:
            await event.answer(str(error))
        return
    await repo.session.refresh(ticket)
    text, markup = await ticket_card(repo, ticket, ctx.settings.tz)
    note = f"{E.BAN_EMOJI} Пользователь заблокирован. Закрыто обращений: {closed}.\n\n"
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer(note + text, reply_markup=markup)  # type: ignore[union-attr]


@router.callback_query(TicketCB.filter(F.action == "banok"))
async def cb_ban_no_reason(callback: CallbackQuery, callback_data: TicketCB, repo: Repo,
                           tickets: TicketService, state: FSMContext, ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    await state.clear()
    if ticket is None:
        return
    await _do_ban(callback, ticket, None, callback.from_user.id, repo, tickets, ctx)
    await safe_answer(callback)


@router.message(AdminTicketStates.ban_reason, F.text)
async def do_ban_reason(message: Message, state: FSMContext, repo: Repo, tickets: TicketService,
                        ctx: AppContext) -> None:
    data = await state.get_data()
    await state.clear()
    ticket = await repo.tickets.get(int(data.get("ban_ticket") or 0))
    if ticket is None:
        await message.answer("Тикет не найден.")
        return
    await _do_ban(message, ticket, (message.text or "")[:500], message.from_user.id, repo, tickets, ctx)  # type: ignore[union-attr]


@router.callback_query(TicketCB.filter(F.action == "unban"))
async def cb_unban(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, tickets: TicketService,
                   ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    await tickets.unban(ticket.user_id)
    await refresh_card(callback, repo, ticket, ctx)
    await safe_answer(callback, "Пользователь разблокирован")


# ------------------------------------------------------------------ история, медиа, ссылки


@router.callback_query(TicketCB.filter(F.action == "hist"))
async def cb_history(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    text, markup = await history_page(repo, ticket, callback_data.page, ctx.settings.tz)
    await show(callback, text, markup)
    await safe_answer(callback)


@router.callback_query(TicketCB.filter(F.action == "media"))
async def cb_media(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, bot: Bot) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    await safe_answer(callback, "Отправляю медиа…")
    items = await repo.tickets.media_messages(ticket.id, limit=20)
    for item in items:
        who = "👤 Пользователь" if item.sender_type == "user" else "🛡 Поддержка"
        label = CONTENT_LABELS.get(item.content_type, "")
        caption = f"{who} · {label} · {ticket.number}"
        if item.html:
            caption += f"\n\n{item.html}"
        try:
            await send_stored(bot, callback.from_user.id, item.content_type, caption[:1024], item.file_id)
        except TelegramAPIError as error:
            await bot.send_message(callback.from_user.id, f"Не удалось показать {label}: {esc(error.message)}")
    await bot.send_message(
        callback.from_user.id,
        f"Показано медиа: {len(items)}",
        reply_markup=kb(btn("К тикету", TicketCB(action="open", id=ticket.id, page=1), icon=E.BACK_EMOJI)),
    )


@router.callback_query(TicketCB.filter(F.action == "links"))
async def cb_links(callback: CallbackQuery, callback_data: TicketCB, repo: Repo, ctx: AppContext) -> None:
    ticket = await _ticket(callback, repo, callback_data.id)
    if ticket is None:
        return
    username = await repo.settings.get("support_username") or ""
    dm = support_dm_link(username, ticket.id)
    user_link = bot_ticket_link(ctx.bot_username, ticket.id) if ctx.bot_username else None
    admin_link = admin_ticket_link(ctx.bot_username, ticket.id) if ctx.bot_username else None
    lines = [f"{E.LINK_EMOJI} <b>Ссылки тикета {ticket.number}</b>\n"]
    if dm:
        lines.append(
            f"<b>В ЛС поддержки с готовым текстом</b> (@{esc(username)}):\n<code>{esc(dm)}</code>\n"
            f"Текст: <i>{esc(support_prefill_text(ticket.id))}</i>\n"
        )
    else:
        lines.append("Username поддержки не задан — Настройки → Username поддержки.\n")
    if user_link:
        lines.append(f"<b>Открыть тикет в боте</b> (для пользователя):\n<code>{esc(user_link)}</code>\n")
    if admin_link:
        lines.append(f"<b>Открыть карточку</b> (для админов):\n<code>{esc(admin_link)}</code>")
    lines.append(
        "\n<i>Telegram подставит текст в поле ввода, отправляет его сам пользователь — "
        "отправить сообщение за него по ссылке невозможно.</i>"
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=kb(
            btn("Скопировать ссылку в ЛС", copy_text=dm) if dm else None,
            btn("К тикету", TicketCB(action="open", id=ticket.id, page=1), icon=E.BACK_EMOJI),
        ),
        disable_web_page_preview=True,
    )
    await safe_answer(callback)


# ------------------------------------------------------------------ прочее


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=kb(back_to_panel()))


__all__ = ["router", "show_list", "STATUS_TITLES"]
