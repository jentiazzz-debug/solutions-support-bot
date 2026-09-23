"""Последний админский роутер: сообщение администратора вне сценария."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from bot.callbacks import AdminCB
from bot.keyboards.common import btn, kb
from config import emoji as E

router = Router(name="admin_idle")


@router.message(StateFilter(None), ~F.text.startswith("/"))
async def admin_idle_message(message: Message) -> None:
    await message.answer(
        f"{E.ADMIN_EMOJI} Чтобы ответить пользователю, нажмите «Ответить» под его сообщением "
        "или просто ответьте (reply) на его сообщение.\n\n/admin — админ-панель",
        reply_markup=kb(btn("Открытые тикеты", AdminCB(section="tickets", action="OPEN"),
                            icon=E.TICKET_EMOJI, style="primary")),
    )
