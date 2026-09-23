"""Клавиатуры тикетов, общие для пользовательской и админской частей."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.callbacks import MenuCB, SupportCB, TicketCB
from bot.keyboards.common import btn, kb
from config import emoji as E
from database.models import Ticket


def user_incoming_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    """Под ответом поддержки у пользователя."""
    return kb(
        btn(f"Ответить · {ticket.number}", SupportCB(action="write", id=ticket.id), icon=E.REPLY_EMOJI,
            style="primary"),
    )


def admin_incoming_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    """Под сообщением пользователя у администратора."""
    return kb(
        [
            btn(f"Ответить · {ticket.number}", TicketCB(action="reply", id=ticket.id),
                icon=E.REPLY_EMOJI, style="primary"),
            btn("Тикет", TicketCB(action="open", id=ticket.id), icon=E.TICKET_EMOJI),
        ]
    )


def new_ticket_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    return kb(
        btn("Открыть тикет", TicketCB(action="open", id=ticket.id), icon=E.TICKET_EMOJI, style="primary"),
        [
            btn("Ответить", TicketCB(action="reply", id=ticket.id), icon=E.REPLY_EMOJI, style="success"),
            btn("Закрыть", TicketCB(action="close", id=ticket.id), icon=E.CLOSE_EMOJI, style="danger"),
        ],
    )


def admin_reply_mode_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    return kb(
        [
            btn("Быстрые ответы", TicketCB(action="quick", id=ticket.id), icon=E.QUICK_EMOJI),
            btn("Закрыть тикет", TicketCB(action="close", id=ticket.id), icon=E.CLOSE_EMOJI,
                style="danger"),
        ],
        btn("Выйти из режима ответа", TicketCB(action="stop", id=ticket.id), icon=E.CROSS_EMOJI),
    )


def user_after_close_kb() -> InlineKeyboardMarkup:
    return kb(
        btn("Новое обращение", SupportCB(action="new"), icon=E.NEW_TICKET_EMOJI, style="primary"),
        btn("Главное меню", MenuCB(section="main"), icon=E.HOME_EMOJI),
    )
