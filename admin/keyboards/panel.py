from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks import AdminCB, MenuCB
from bot.keyboards.common import btn, kb
from config import emoji as E


def panel_kb(is_owner: bool, open_count: int) -> InlineKeyboardMarkup:
    tickets_text = f"Тикеты · {open_count}" if open_count else "Тикеты"
    return kb(
        [
            btn(tickets_text, AdminCB(section="tickets"), icon=E.TICKET_EMOJI, style="primary"),
            btn("Статистика", AdminCB(section="stats"), icon=E.STATS_EMOJI),
        ],
        [
            btn("Рассылка", AdminCB(section="bc"), icon=E.BROADCAST_EMOJI),
            btn("Быстрые ответы", AdminCB(section="qr"), icon=E.QUICK_EMOJI),
        ],
        [
            btn("Проекты", AdminCB(section="proj"), icon=E.PROJECTS_EMOJI),
            btn("Портфолио", AdminCB(section="links"), icon=E.PORTFOLIO_EMOJI),
        ],
        [
            btn("Главное меню", AdminCB(section="menu"), icon=E.MENU_EMOJI),
            btn("Тексты", AdminCB(section="texts"), icon=E.EDIT_EMOJI),
        ],
        [
            btn("Категории", AdminCB(section="cats"), icon=E.CATEGORY_EMOJI),
            btn("Блокировки", AdminCB(section="bans"), icon=E.BAN_EMOJI),
        ],
        btn("Настройки", AdminCB(section="set"), icon=E.SETTINGS_EMOJI),
        # Доп. аккаунт и список админов — только владельцам (ADMIN_IDS).
        [
            btn("Доп. аккаунт", AdminCB(section="acc"), icon=E.ACCOUNT_EMOJI),
            btn("Администраторы", AdminCB(section="admins"), icon=E.SHIELD_EMOJI),
        ] if is_owner else None,
        btn("Пользовательское меню", MenuCB(section="main"), icon=E.HOME_EMOJI),
    )


def back_to_panel() -> InlineKeyboardButton:
    return btn("Админ-панель", AdminCB(section="home"), icon=E.ADMIN_EMOJI)


def back(section: str, text: str = "Назад", **kwargs) -> InlineKeyboardButton:
    return btn(text, AdminCB(section=section, **kwargs), icon=E.BACK_EMOJI)


def cancel_kb(section: str) -> InlineKeyboardMarkup:
    return kb(btn("Отмена", AdminCB(section=section), icon=E.CROSS_EMOJI))


def confirm_kb(yes: AdminCB, no: AdminCB, yes_text: str = "Да, удалить") -> InlineKeyboardMarkup:
    return kb([btn(yes_text, yes, style="danger"), btn("Отмена", no)])
