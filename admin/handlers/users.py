"""Блокировки пользователей в поддержке и список администраторов."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, cancel_kb
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.filters import IsOwner
from bot.keyboards.common import btn, kb, pager
from bot.services.render import safe_answer, show
from bot.states import AdminManageStates
from config import emoji as E
from database.repositories import Repo
from support.ticket_service import TicketError, TicketService
from utils.text import esc, fmt_dt, truncate

router = Router(name="admin_users")
B = "bans"
A = "admins"
PAGE = 10


async def _user_label(repo: Repo, user_id: int) -> str:
    user = await repo.users.get(user_id)
    if user is None:
        return str(user_id)
    return f"{user.mention} ({user_id})"


# =================================================================== БЛОКИРОВКИ


async def show_bans(event: Message | CallbackQuery, repo: Repo, page: int = 0) -> None:
    items, total = await repo.bans.page(page * PAGE, PAGE)
    buttons = [btn(truncate(await _user_label(repo, b.user_id), 50), AdminCB(section=B, action="view", id=b.user_id))
               for b in items]
    await show(event, (
        f"{E.BAN_EMOJI} <b>Заблокированные в поддержке</b> · {total}\n\n"
        "Заблокированный пользователь не может создавать обращения; остальные разделы бота ему доступны."
    ), kb(
        *buttons,
        pager(lambda p: AdminCB(section=B, page=p), page, total, PAGE),
        btn("Заблокировать по ID", AdminCB(section=B, action="add"), icon=E.BAN_EMOJI, style="danger"),
        back_to_panel(),
    ))


@router.callback_query(AdminCB.filter((F.section == B) & (F.action == "")))
async def bans_list(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_bans(callback, repo, callback_data.page)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == B) & (F.action == "view")))
async def ban_view(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    ban = await repo.bans.get(callback_data.id)
    if ban is None:
        await show_bans(callback, repo)
        return await safe_answer(callback, "Уже разблокирован")
    await show(callback, (
        f"{E.BAN_EMOJI} <b>{esc(await _user_label(repo, ban.user_id))}</b>\n\n"
        f"Заблокирован: {fmt_dt(ban.created_at, ctx.settings.tz)}\n"
        f"Кем: <code>{ban.banned_by or '—'}</code>\n"
        f"Причина: {esc(ban.reason or '—')}"
    ), kb(
        btn("Разблокировать", AdminCB(section=B, action="unban", id=ban.user_id), icon=E.UNLOCK_EMOJI,
            style="success"),
        back(B),
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == B) & (F.action == "unban")))
async def ban_remove(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, tickets: TicketService) -> None:
    ok = await tickets.unban(callback_data.id)
    await show_bans(callback, repo)
    await safe_answer(callback, "Пользователь разблокирован" if ok else "Не был заблокирован")


@router.callback_query(AdminCB.filter((F.section == B) & (F.action == "add")))
async def ban_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminManageStates.ban_user)
    await show(callback, "Отправьте Telegram ID (или @username, если пользователь уже писал боту) "
                         "и, через пробел, причину:\n<code>123456789 спам</code>", cancel_kb(B))
    await safe_answer(callback)


@router.message(AdminManageStates.ban_user, F.text)
async def ban_add_do(message: Message, state: FSMContext, repo: Repo, tickets: TicketService) -> None:
    target, _, reason = (message.text or "").strip().partition(" ")
    if target.startswith("@"):
        user = await repo.users.find_by_username(target)
        user_id = user.id if user else None
    else:
        user_id = int(target) if target.isdigit() else None
    if user_id is None:
        await message.answer("Пользователь не найден. Укажите числовой ID.")
        return
    await state.clear()
    try:
        closed = await tickets.ban(user_id, message.from_user.id, reason.strip() or None)  # type: ignore[union-attr]
    except TicketError as error:
        await message.answer(str(error))
        return
    await message.answer(f"{E.BAN_EMOJI} Пользователь <code>{user_id}</code> заблокирован. Закрыто обращений: {closed}.")
    await show_bans(message, repo)


# =================================================================== АДМИНИСТРАТОРЫ (только владельцы)

router_owner = Router(name="admin_owner")
router_owner.message.filter(IsOwner())
router_owner.callback_query.filter(IsOwner())


async def show_admins(event: Message | CallbackQuery, repo: Repo, ctx: AppContext) -> None:
    rows = {a.user_id: a for a in await repo.admins.all()}
    ids = sorted(ctx.admins.owners | set(rows))
    lines = [f"{E.SHIELD_EMOJI} <b>Администраторы</b>\n",
             "👑 — владелец из ADMIN_IDS (.env), снять можно только там.\n"
             "🔔/🔕 — получает ли уведомления о тикетах.\n"]
    buttons = []
    for uid in ids:
        row = rows.get(uid)
        notify = row.notify if row else True
        crown = "👑 " if uid in ctx.admins.owners else ""
        label = await _user_label(repo, uid)
        lines.append(f"{crown}{'🔔' if notify else '🔕'} {esc(label)}")
        buttons.append(btn(truncate(f"{crown}{'🔔' if notify else '🔕'} {label}", 50),
                           AdminCB(section=A, action="view", id=uid)))
    await show(event, "\n".join(lines), kb(
        *buttons,
        btn("Добавить администратора", AdminCB(section=A, action="add"), icon=E.PLUS_EMOJI, style="success"),
        back_to_panel(),
    ))


@router_owner.callback_query(AdminCB.filter((F.section == A) & (F.action == "")))
async def admins_list(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await state.set_state(None)
    await show_admins(callback, repo, ctx)
    await safe_answer(callback)


@router_owner.callback_query(AdminCB.filter((F.section == A) & (F.action == "view")))
async def admin_view(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    uid = callback_data.id
    row = await repo.admins.get(uid)
    notify = row.notify if row else True
    is_owner = uid in ctx.admins.owners
    await show(callback, (
        f"{E.SHIELD_EMOJI} <b>{esc(await _user_label(repo, uid))}</b>\n"
        f"{'Владелец (ADMIN_IDS)' if is_owner else 'Администратор'}\n"
        f"Уведомления о тикетах: {'включены' if notify else 'выключены'}"
    ), kb(
        btn("Выключить уведомления" if notify else "Включить уведомления",
            AdminCB(section=A, action="notify", id=uid), icon=E.BELL_EMOJI),
        btn("Снять права", AdminCB(section=A, action="remove", id=uid), icon=E.TRASH_EMOJI, style="danger")
        if not is_owner else None,
        back(A),
    ))
    await safe_answer(callback)


@router_owner.callback_query(AdminCB.filter((F.section == A) & (F.action == "notify")))
async def admin_notify(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    row = await repo.admins.ensure(callback_data.id, added_by=callback.from_user.id)
    row.notify = not row.notify
    await repo.commit()
    await ctx.admins.reload(repo)
    await show_admins(callback, repo, ctx)
    await safe_answer(callback, "Уведомления включены" if row.notify else "Уведомления выключены")


@router_owner.callback_query(AdminCB.filter((F.section == A) & (F.action == "remove")))
async def admin_remove(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    if callback_data.id in ctx.admins.owners:
        return await safe_answer(callback, "Владельца можно убрать только из ADMIN_IDS", alert=True)
    row = await repo.admins.get(callback_data.id)
    if row is not None:
        await repo.admins.delete(row)
        await repo.commit()
    await ctx.admins.reload(repo)
    await show_admins(callback, repo, ctx)
    await safe_answer(callback, "Права сняты")


@router_owner.callback_query(AdminCB.filter((F.section == A) & (F.action == "add")))
async def admin_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminManageStates.add)
    await show(callback, "Отправьте Telegram ID нового администратора (узнать ID можно в @ScanMyIdRobot) "
                         "или @username, если он уже писал боту:", cancel_kb(A))
    await safe_answer(callback)


@router_owner.message(AdminManageStates.add, F.text)
async def admin_add_do(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("@"):
        user = await repo.users.find_by_username(text)
        user_id = user.id if user else None
    else:
        user_id = int(text) if text.isdigit() else None
    if user_id is None:
        await message.answer("Не нашёл пользователя. Укажите числовой ID.")
        return
    await repo.admins.ensure(user_id, added_by=message.from_user.id)  # type: ignore[union-attr]
    await repo.commit()
    await ctx.admins.reload(repo)
    await state.clear()
    await message.answer(f"{E.CLOSE_EMOJI} <code>{user_id}</code> теперь администратор. Панель: /admin")
    await show_admins(message, repo, ctx)
