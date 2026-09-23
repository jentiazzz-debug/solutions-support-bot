"""Админская часть. Все роутеры закрыты фильтром IsAdmin на уровне
родительского роутера — права проверяются на КАЖДОМ сообщении и нажатии."""

from aiogram import Router

from admin.handlers import (
    accounts,
    broadcast,
    content,
    idle,
    menu_editor,
    panel,
    projects,
    quick_replies,
    stats,
    tickets,
    users,
)
from bot.filters import IsAdmin
from bot.handlers.routing import attach


def admin_router() -> Router:
    root = Router(name="admin")
    root.message.filter(IsAdmin())
    root.callback_query.filter(IsAdmin())
    attach(
        root,
        panel.router,
        tickets.router,
        quick_replies.router,
        projects.router,
        menu_editor.router,
        content.router,
        broadcast.router,
        stats.router,
        users.router,
        users.router_owner,
        accounts.router,
        idle.router,
    )
    return root
