from __future__ import annotations

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from admin.keyboards.panel import back_to_panel
from admin.services.stats_service import collect, render_chart, series
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.keyboards.common import btn, kb
from bot.services.render import safe_answer, show
from config import emoji as E
from database.repositories import Repo
from utils.text import esc, fmt_number

router = Router(name="admin_stats")
S = "stats"


def _stats_kb():
    return kb(
        [
            btn("График 7 дней", AdminCB(section=S, action="chart", page=7), icon=E.STATS_EMOJI),
            btn("График 30 дней", AdminCB(section=S, action="chart", page=30), icon=E.STATS_EMOJI),
        ],
        btn("Обновить", AdminCB(section=S), icon=E.PROGRESS_EMOJI),
        back_to_panel(),
    )


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def cb_stats(callback: CallbackQuery, repo: Repo, ctx: AppContext) -> None:
    s = await collect(repo, ctx.settings.tz)
    categories = "\n".join(f"• {esc(title)} — {count}" for title, count in s.by_category) or "—"
    text = (
        f"{E.STATS_EMOJI} <b>Статистика</b>\n\n"
        f"{E.USERS_EMOJI} <b>Пользователи</b>\n"
        f"Всего: <b>{fmt_number(s.users_total)}</b>\n"
        f"Новых сегодня: <b>{s.users_today}</b> · за неделю: <b>{s.users_week}</b> · за месяц: <b>{s.users_month}</b>\n"
        f"Активных за 24 ч: <b>{s.active_day}</b> · за 7 дней: <b>{s.active_week}</b>\n"
        f"Заблокировали бота: <b>{s.blocked_bot}</b>\n"
        f"Заблокированы в поддержке: <b>{s.banned}</b>\n\n"
        f"{E.TICKET_EMOJI} <b>Тикеты</b>\n"
        f"Всего: <b>{s.tickets_total}</b>\n"
        f"🟢 Открытые: <b>{s.tickets_open}</b> · 🟡 в работе: <b>{s.tickets_in_progress}</b>\n"
        f"⚪ Закрытые: <b>{s.tickets_closed}</b> · ⛔ заблок.: <b>{s.tickets_banned}</b>\n"
        f"{E.MESSAGE_EMOJI} Сообщений в поддержке: <b>{fmt_number(s.messages_total)}</b>\n\n"
        f"{E.CATEGORY_EMOJI} <b>По категориям</b>\n{categories}"
    )
    await show(callback, text, _stats_kb())
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "chart")))
async def cb_chart(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    days = 30 if callback_data.page == 30 else 7
    await safe_answer(callback, "Строю график…")
    users, tickets = await series(repo, ctx.settings.tz, days)
    png = render_chart(users, tickets, f"Solutions · последние {days} дней")
    if isinstance(callback.message, Message):
        await callback.message.answer_photo(
            BufferedInputFile(png, filename=f"stats_{days}d.png"),
            caption=(f"{E.STATS_EMOJI} За {days} дней: новых пользователей <b>{sum(v for _, v in users)}</b>, "
                     f"тикетов <b>{sum(v for _, v in tickets)}</b>"),
            reply_markup=kb(back_to_panel()),
        )
