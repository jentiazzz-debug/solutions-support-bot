"""Клавиатуры пользовательской части."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks import AdminCB, MenuCB, ProjectCB, SupportCB
from bot.keyboards.common import btn, chunks, kb
from config import emoji as E
from database.models import MenuButton, PortfolioLink, Project, Ticket, TicketCategory

SECTION_KEYS = {"about", "support", "portfolio", "ads"}


def main_menu_kb(buttons: Sequence[MenuButton], is_admin: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    pending_half: InlineKeyboardButton | None = None
    for item in buttons:
        if not item.is_enabled:
            continue
        if item.key == "link":
            if not item.url:
                continue
            button = btn(item.text, url=item.url, icon=item.icon_emoji_id, style=item.style)
        elif item.key in SECTION_KEYS:
            button = btn(item.text, MenuCB(section=item.key), icon=item.icon_emoji_id, style=item.style)
        else:
            continue
        if item.row_width >= 2:
            if pending_half is None:
                pending_half = button
            else:
                rows.append([pending_half, button])
                pending_half = None
            continue
        if pending_half is not None:
            rows.append([pending_half])
            pending_half = None
        rows.append([button])
    if pending_half is not None:
        rows.append([pending_half])
    if is_admin:
        rows.append([btn("Админ-панель", AdminCB(section="home"), icon=E.ADMIN_EMOJI)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_home_row() -> InlineKeyboardButton:
    return btn("Главное меню", MenuCB(section="main"), icon=E.HOME_EMOJI)


def about_kb(projects: Sequence[Project]) -> InlineKeyboardMarkup:
    buttons = [btn(p.title, ProjectCB(id=p.id)) for p in projects]
    return kb(
        *chunks(buttons, 2),
        btn("Наше портфолио", MenuCB(section="portfolio"), icon=E.PORTFOLIO_EMOJI, style="primary"),
        back_home_row(),
    )


def project_kb(project: Project) -> InlineKeyboardMarkup:
    rows: list = []
    if project.link:
        rows.append(btn("Открыть", url=project.link, icon=E.ROCKET_EMOJI, style="primary"))
    extra = [
        btn(link.get("title", "Ссылка")[:64], url=link["url"])
        for link in (project.extra_links or [])
        if isinstance(link, dict) and link.get("url")
    ]
    rows.extend(chunks(extra, 2))
    rows.append(btn("Все проекты", MenuCB(section="about"), icon=E.BACK_EMOJI))
    return kb(*rows)


def portfolio_kb(links: Sequence[PortfolioLink]) -> InlineKeyboardMarkup:
    return kb(
        *[btn(link.title, url=link.url, icon=link.icon_emoji_id, style=link.style) for link in links],
        back_home_row(),
    )


def ads_kb(manager_url: str | None) -> InlineKeyboardMarkup:
    return kb(
        btn("Заказать рекламу", SupportCB(action="ads_order"), icon=E.ADS_EMOJI, style="success"),
        btn("Написать менеджеру", url=manager_url, icon=E.MESSAGE_EMOJI) if manager_url else None,
        back_home_row(),
    )


def support_kb(active_count: int) -> InlineKeyboardMarkup:
    my_text = f"Мои обращения · {active_count}" if active_count else "Мои обращения"
    return kb(
        btn("Создать обращение", SupportCB(action="new"), icon=E.NEW_TICKET_EMOJI, style="primary"),
        btn(my_text, SupportCB(action="my"), icon=E.MY_TICKETS_EMOJI),
        back_home_row(),
    )


def categories_kb(categories: Sequence[TicketCategory]) -> InlineKeyboardMarkup:
    buttons = [btn(c.label, SupportCB(action="cat", id=c.id)) for c in categories]
    return kb(*chunks(buttons, 2), btn("Назад", MenuCB(section="support"), icon=E.BACK_EMOJI))


def cancel_kb() -> InlineKeyboardMarkup:
    return kb(btn("Отмена", MenuCB(section="support"), icon=E.CROSS_EMOJI))


def my_tickets_kb(tickets: Sequence[Ticket]) -> InlineKeyboardMarkup:
    buttons = [
        btn(f"{t.number} · {t.category_title}"[:60], SupportCB(action="open", id=t.id)) for t in tickets
    ]
    return kb(*buttons, btn("Назад", MenuCB(section="support"), icon=E.BACK_EMOJI))


def user_ticket_kb(ticket: Ticket, dm_link: str | None) -> InlineKeyboardMarkup:
    if not ticket.is_active:
        return kb(btn("Назад", SupportCB(action="my"), icon=E.BACK_EMOJI))
    return kb(
        btn("Написать в обращение", SupportCB(action="write", id=ticket.id), icon=E.REPLY_EMOJI,
            style="primary"),
        btn("Написать в ЛС поддержки", url=dm_link, icon=E.LINK_EMOJI) if dm_link else None,
        btn("Закрыть обращение", SupportCB(action="close", id=ticket.id), icon=E.CLOSE_EMOJI,
            style="danger"),
        btn("Назад", SupportCB(action="my"), icon=E.BACK_EMOJI),
    )


def confirm_close_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    return kb(
        [
            btn("Да, закрыть", SupportCB(action="close_yes", id=ticket.id), style="danger"),
            btn("Нет", SupportCB(action="open", id=ticket.id)),
        ]
    )


def choose_ticket_kb(tickets: Sequence[Ticket]) -> InlineKeyboardMarkup:
    return kb(
        *[
            btn(f"{t.number} · {t.category_title}"[:60], SupportCB(action="write", id=t.id))
            for t in tickets
        ],
        btn("Создать обращение", SupportCB(action="new"), icon=E.NEW_TICKET_EMOJI, style="primary"),
    )
