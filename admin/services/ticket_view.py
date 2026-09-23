"""Карточка тикета и история переписки для администратора."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardMarkup

from admin.keyboards.panel import back_to_panel
from bot.callbacks import AdminCB, TicketCB
from bot.keyboards.common import btn, kb, pager
from config import emoji as E
from database.models import SenderType, Ticket, TicketMessage
from database.repositories import Repo
from support.message_service import CONTENT_LABELS
from utils.text import esc, fmt_dt, truncate

STATUS_TITLES = {
    "OPEN": "🟢 Открыт",
    "IN_PROGRESS": "🟡 В работе",
    "CLOSED": "⚪ Закрыт",
    "BANNED": "⛔ Заблокирован",
}
SENDER_ICONS = {SenderType.USER.value: "👤", SenderType.ADMIN.value: "🛡", SenderType.SYSTEM.value: "⚙️"}
HISTORY_PAGE = 15


def message_line(msg: TicketMessage, tz, limit: int = 300) -> str:
    icon = SENDER_ICONS.get(msg.sender_type, "•")
    label = CONTENT_LABELS.get(msg.content_type, "📦")
    body = esc(truncate(msg.text or "", limit)) if msg.text else ""
    content = " ".join(p for p in (f"<i>{label}</i>" if label else "", body) if p) or "—"
    return f"{icon} <b>{fmt_dt(msg.created_at, tz, '%d.%m %H:%M')}</b> {content}"


async def ticket_card(repo: Repo, ticket: Ticket, tz) -> tuple[str, InlineKeyboardMarkup]:
    user = await repo.users.get(ticket.user_id)
    banned = await repo.bans.is_banned(ticket.user_id)
    total_user_tickets = await repo.tickets.count_for_user(ticket.user_id)
    msg_count = await repo.tickets.count_messages(ticket.id)
    media_count = await repo.tickets.count_media(ticket.id)
    last = list(reversed(await repo.tickets.messages(ticket.id, limit=6, newest_first=True)))

    username = f"@{esc(user.username)}" if user and user.username else "—"
    name = esc(user.full_name if user else ticket.full_name)
    lines = [
        f"{E.TICKET_EMOJI} <b>Тикет {ticket.number}</b> · {STATUS_TITLES.get(ticket.status, ticket.status)}",
        "",
        f"{E.USER_EMOJI} <b>{name}</b> {username}",
        f"ID: <code>{ticket.user_id}</code> · тикетов всего: {total_user_tickets}"
        + (" · ⛔ заблокирован" if banned else "")
        + (" · 🚫 бот заблокирован" if user and user.is_blocked_bot else ""),
        f"{E.CATEGORY_EMOJI} Категория: {esc(ticket.category_title)}",
        f"{E.TIME_EMOJI} Создан: {fmt_dt(ticket.created_at, tz)}",
        f"{E.MESSAGE_EMOJI} Сообщений: {msg_count}" + (f" · медиа: {media_count}" if media_count else ""),
    ]
    if ticket.assigned_admin_id:
        lines.append(f"{E.SHIELD_EMOJI} Отвечает: <code>{ticket.assigned_admin_id}</code>")
    if ticket.closed_at:
        lines.append(f"Закрыт: {fmt_dt(ticket.closed_at, tz)}")
        if ticket.close_reason:
            lines.append(f"Причина: {esc(truncate(ticket.close_reason, 200))}")
    if last:
        lines += ["", f"{E.HISTORY_EMOJI} <b>Последние сообщения</b>"]
        lines += [message_line(m, tz, 180) for m in last]
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "…"
    return text, ticket_kb(ticket, banned, media_count)


def ticket_kb(ticket: Ticket, banned: bool, media_count: int) -> InlineKeyboardMarkup:
    tid = ticket.id
    rows: list = []
    if ticket.is_active:
        rows.append([
            btn("Ответить", TicketCB(action="reply", id=tid), icon=E.REPLY_EMOJI, style="primary"),
            btn("Быстрые ответы", TicketCB(action="quick", id=tid), icon=E.QUICK_EMOJI),
        ])
        row = []
        if ticket.status == "OPEN":
            row.append(btn("Взять в работу", TicketCB(action="take", id=tid), icon=E.PROGRESS_EMOJI))
        row.append(btn("Закрыть", TicketCB(action="close", id=tid), icon=E.CLOSE_EMOJI, style="success"))
        rows.append(row)
        rows.append(btn("Закрыть с причиной", TicketCB(action="closer", id=tid), icon=E.EDIT_EMOJI))
    rows.append([
        btn("История", TicketCB(action="hist", id=tid), icon=E.HISTORY_EMOJI),
        btn(f"Медиа · {media_count}", TicketCB(action="media", id=tid), icon=E.EYE_EMOJI)
        if media_count else None,
        btn("Ссылки", TicketCB(action="links", id=tid), icon=E.LINK_EMOJI),
    ])
    if banned:
        rows.append(btn("Разблокировать пользователя", TicketCB(action="unban", id=tid), icon=E.UNLOCK_EMOJI))
    else:
        rows.append(btn("Заблокировать пользователя", TicketCB(action="ban", id=tid), icon=E.BAN_EMOJI,
                        style="danger"))
    rows.append([btn("К списку", AdminCB(section="tickets"), icon=E.BACK_EMOJI), back_to_panel()])
    return kb(*rows)


async def history_page(
    repo: Repo, ticket: Ticket, page: int, tz
) -> tuple[str, InlineKeyboardMarkup]:
    total = await repo.tickets.count_messages(ticket.id)
    pages = max((total + HISTORY_PAGE - 1) // HISTORY_PAGE, 1)
    page = min(max(page, 0), pages - 1)
    msgs: Sequence[TicketMessage] = await repo.tickets.messages(
        ticket.id, offset=page * HISTORY_PAGE, limit=HISTORY_PAGE
    )
    header = f"{E.HISTORY_EMOJI} <b>История {ticket.number}</b> · {total} сообщ.\n\n"
    body_lines: list[str] = []
    budget = 4000 - len(header)
    per_msg = max(budget // max(len(msgs), 1) - 60, 60)
    for m in msgs:
        body_lines.append(message_line(m, tz, per_msg))
    body = "\n\n".join(body_lines) or "Сообщений нет."
    text = (header + body)[:4090]
    nav = pager(lambda p: TicketCB(action="hist", id=ticket.id, page=p), page, total, HISTORY_PAGE)
    return text, kb(nav, btn("К тикету", TicketCB(action="open", id=ticket.id, page=1), icon=E.BACK_EMOJI))
