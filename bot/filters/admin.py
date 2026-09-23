from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.context import AppContext


class IsAdmin(BaseFilter):
    """Пропускает только администраторов. Проверяется на КАЖДОМ апдейте:
    ставится фильтром на весь админский роутер (message + callback_query)."""

    async def __call__(self, event: TelegramObject, event_from_user=None, ctx: AppContext | None = None,
                       **_: Any) -> bool:
        if ctx is None or event_from_user is None:
            return False
        return ctx.admins.is_admin(event_from_user.id)


class IsOwner(BaseFilter):
    """Владельцы из ADMIN_IDS — управляют списком администраторов."""

    async def __call__(self, event: TelegramObject, event_from_user=None, ctx: AppContext | None = None,
                       **_: Any) -> bool:
        if ctx is None or event_from_user is None:
            return False
        return ctx.admins.is_owner(event_from_user.id)
