"""Типизированные callback data.

aiogram валидирует их через pydantic: подделанная или устаревшая строка
не распарсится и до хендлера не дойдёт (её перехватит fallback-хендлер).
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    # main / about / support / portfolio / ads / projects
    section: str
    page: int = 0


class ProjectCB(CallbackData, prefix="p"):
    id: int
    page: int = 0


class SupportCB(CallbackData, prefix="s"):
    # new / my / cat / open / write / close / close_yes / ads_order
    action: str
    id: int = 0


class AdminCB(CallbackData, prefix="a"):
    # section: home / stats / tickets / bc / qr / proj / links / cats / menu /
    #          bans / admins / acc / texts
    section: str
    action: str = ""
    id: int = 0
    page: int = 0
    extra: str = ""


class TicketCB(CallbackData, prefix="t"):
    # open / reply / quick / qsend / take / close / closer / ban / unban /
    # hist / media / links / stop
    action: str
    id: int
    page: int = 0
    extra: int = 0
