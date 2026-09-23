"""«Добавить аккаунт» — дополнительный Telegram-аккаунт для уведомлений о тикетах.

Доступно только владельцам (ADMIN_IDS). Код и пароль 2FA вводит сам
владелец аккаунта; сообщения с ними бот сразу удаляет из чата и нигде
не сохраняет. Альтернатива без ввода кода в чат — консольный скрипт
scripts/connect_account.py (см. README).
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, confirm_kb
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.filters import IsOwner
from bot.keyboards.common import btn, kb
from bot.services.render import safe_answer, show
from bot.states import AccountStates
from config import emoji as E
from database.models import ConnectedAccount
from database.repositories import Repo
from support.account_service import AccountError
from utils.text import esc, fmt_dt

log = logging.getLogger(__name__)
router = Router(name="admin_accounts")
router.message.filter(IsOwner())
router.callback_query.filter(IsOwner())
S = "acc"


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


def _cancel_kb():
    return kb(btn("Отмена", AdminCB(section=S, action="cancel"), icon=E.CROSS_EMOJI))


async def show_accounts(event: Message | CallbackQuery, repo: Repo, ctx: AppContext) -> None:
    if not ctx.accounts.available:
        await show(event, (
            f"{E.ACCOUNT_EMOJI} <b>Дополнительный аккаунт</b>\n\n"
            f"{E.WARNING_EMOJI} Функция не настроена: {esc(ctx.accounts.unavailable_reason())}\n\n"
            "Инструкция — в README, раздел «Дополнительный аккаунт»."
        ), kb(back_to_panel()))
        return
    accounts = await repo.accounts.all()
    lines = [
        f"{E.ACCOUNT_EMOJI} <b>Дополнительный аккаунт</b>\n",
        "Подключённый аккаунт присылает уведомления о новых тикетах в обычный чат "
        "(например, на ваш основной аккаунт) — так они не теряются среди сообщений бота.\n",
    ]
    for a in accounts:
        status = "🟢" if a.is_active and not a.last_error else ("🔴" if a.last_error else "⚪")
        lines.append(f"{status} {esc(a.display_name or '')} {('@' + esc(a.username)) if a.username else ''} "
                     f"· {esc(a.phone_masked or '')} → {esc(a.notify_target or 'me')}")
    if not accounts:
        lines.append("Аккаунтов пока нет.")
    await show(event, "\n".join(lines), kb(
        *[btn(f"{a.display_name or a.phone_masked}", AdminCB(section=S, action="view", id=a.id)) for a in accounts],
        btn("Добавить аккаунт", AdminCB(section=S, action="add"), icon=E.PLUS_EMOJI, style="primary"),
        back_to_panel(),
    ))


async def show_account(event: Message | CallbackQuery, repo: Repo, ctx: AppContext, account_id: int) -> None:
    a = await repo.accounts.get(account_id)
    if a is None:
        return await show_accounts(event, repo, ctx)
    aid = a.id
    await show(event, (
        f"{E.ACCOUNT_EMOJI} <b>{esc(a.display_name or '')}</b> {('@' + esc(a.username)) if a.username else ''}\n\n"
        f"Телефон: {esc(a.phone_masked or '—')}\n"
        f"ID: <code>{a.tg_user_id}</code>\n"
        f"Уведомления → {esc(a.notify_target or 'me')}\n"
        f"Статус: {'включён' if a.is_active else 'выключен'}\n"
        f"Подключён: {fmt_dt(a.created_at, ctx.settings.tz)}\n"
        f"Последняя ошибка: {esc(a.last_error or '—')}\n\n"
        "<i>Сессия хранится зашифрованной (Fernet).</i>"
    ), kb(
        [btn("Тест", AdminCB(section=S, action="test", id=aid), icon=E.SEND_EMOJI),
         btn("Получатель", AdminCB(section=S, action="target", id=aid), icon=E.USER_EMOJI)],
        btn("Выключить" if a.is_active else "Включить", AdminCB(section=S, action="toggle", id=aid)),
        btn("Отключить и удалить", AdminCB(section=S, action="del", id=aid), icon=E.TRASH_EMOJI, style="danger"),
        back(S),
    ))


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def acc_home(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await state.set_state(None)
    await show_accounts(callback, repo, ctx)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "view")))
async def acc_view(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    await show_account(callback, repo, ctx, callback_data.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "cancel")))
async def acc_cancel(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await ctx.accounts.cancel_login(callback.from_user.id)
    await state.clear()
    await show_accounts(callback, repo, ctx)
    await safe_answer(callback, "Отменено")


# ------------------------------------------------------------------ вход


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "add")))
async def acc_add(callback: CallbackQuery, state: FSMContext, ctx: AppContext) -> None:
    if not ctx.accounts.available:
        return await safe_answer(callback, ctx.accounts.unavailable_reason()[:190], alert=True)
    await state.set_state(AccountStates.phone)
    await show(callback, (
        f"{E.ACCOUNT_EMOJI} <b>Подключение аккаунта · 1/3</b>\n\n"
        f"{E.SHIELD_EMOJI} Подключайте только <b>свой</b> аккаунт. Вход идёт через официальный "
        "протокол Telegram; код и пароль не сохраняются, а ваши сообщения с ними бот сразу удаляет.\n\n"
        "Отправьте номер телефона аккаунта в международном формате: <code>+79991234567</code>"
    ), _cancel_kb())
    await safe_answer(callback)


@router.message(AccountStates.phone, F.text)
async def acc_phone(message: Message, state: FSMContext, ctx: AppContext) -> None:
    await _delete(message)
    try:
        await ctx.accounts.begin_login(message.from_user.id, message.text or "")  # type: ignore[union-attr]
    except AccountError as error:
        await message.answer(f"{E.WARNING_EMOJI} {esc(error)}", reply_markup=_cancel_kb())
        return
    await state.set_state(AccountStates.code)
    await message.answer(
        f"{E.ACCOUNT_EMOJI} <b>Подключение аккаунта · 2/3</b>\n\n"
        "Telegram отправил код в приложение (или SMS). Введите его <b>через пробелы</b>: "
        "<code>1 2 3 4 5</code>\n\n"
        "<i>Если отправить код одним числом, Telegram посчитает, что им поделились, и аннулирует его.</i>",
        reply_markup=_cancel_kb(),
    )


@router.message(AccountStates.code, F.text)
async def acc_code(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await _delete(message)
    admin_id = message.from_user.id  # type: ignore[union-attr]
    try:
        result = await ctx.accounts.submit_code(admin_id, message.text or "")
    except AccountError as error:
        if not ctx.accounts.is_logging_in(admin_id):
            await state.clear()
        await message.answer(f"{E.WARNING_EMOJI} {esc(error)}", reply_markup=_cancel_kb())
        return
    if result is None:
        await state.set_state(AccountStates.password)
        await message.answer(
            f"{E.ACCOUNT_EMOJI} <b>Подключение аккаунта · 2FA</b>\n\n"
            "На аккаунте включён облачный пароль. Отправьте его — сообщение будет сразу удалено.",
            reply_markup=_cancel_kb(),
        )
        return
    await _saved(message, state, repo, ctx, result)


@router.message(AccountStates.password, F.text)
async def acc_password(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await _delete(message)
    try:
        result = await ctx.accounts.submit_password(message.from_user.id, message.text or "")  # type: ignore[union-attr]
    except AccountError as error:
        await message.answer(f"{E.WARNING_EMOJI} {esc(error)}", reply_markup=_cancel_kb())
        return
    await _saved(message, state, repo, ctx, result)


async def _saved(message: Message, state: FSMContext, repo: Repo, ctx: AppContext, result) -> None:
    account = await repo.accounts.add(ConnectedAccount(
        tg_user_id=result.tg_user_id,
        username=result.username,
        display_name=result.display_name,
        phone_masked=result.phone_masked,
        session_encrypted=result.session_encrypted,
        notify_target="me",
        added_by=message.from_user.id if message.from_user else None,
    ))
    await repo.commit()
    log.info("Подключён доп. аккаунт #%s (%s)", account.id, result.phone_masked)
    await state.set_state(AccountStates.target)
    await state.update_data(account_id=account.id)
    own = message.from_user.username if message.from_user else None
    await message.answer(
        f"{E.CLOSE_EMOJI} Аккаунт <b>{esc(result.display_name)}</b> подключён.\n\n"
        f"<b>3/3 · Куда присылать уведомления?</b>\n"
        "Отправьте @username или числовой ID получателя (например, ваш основной аккаунт), "
        "либо выберите вариант ниже.",
        reply_markup=kb(
            btn(f"Мне · @{own}", AdminCB(section=S, action="settarget", id=account.id, extra=f"@{own}"))
            if own else None,
            btn("В «Избранное» аккаунта", AdminCB(section=S, action="settarget", id=account.id, extra="me")),
        ),
    )


async def _apply_target(event: Message | CallbackQuery, repo: Repo, ctx: AppContext, account_id: int,
                        target: str) -> None:
    account = await repo.accounts.get(account_id)
    if account is None:
        return
    account.notify_target = target[:128]
    await repo.commit()
    try:
        await ctx.accounts.send(account.id, account.session_encrypted, account.notify_target,
                                "✅ Уведомления о новых тикетах Solutions подключены.")
        account.last_error = None
        note = f"{E.CLOSE_EMOJI} Тестовое уведомление отправлено → {esc(target)}"
    except Exception as error:  # noqa: BLE001
        account.last_error = str(error)[:500]
        note = (f"{E.WARNING_EMOJI} Не удалось отправить тест → {esc(target)}: {esc(error)}\n"
                "Если это numeric ID — аккаунт должен хотя бы раз переписываться с получателем; "
                "надёжнее указать @username.")
    await repo.commit()
    target_msg = event.message if isinstance(event, CallbackQuery) else event
    await target_msg.answer(note)  # type: ignore[union-attr]
    await show_account(target_msg, repo, ctx, account.id)  # type: ignore[arg-type]


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "settarget")))
async def acc_set_target_cb(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo,
                            ctx: AppContext) -> None:
    await state.clear()
    await safe_answer(callback)
    await _apply_target(callback, repo, ctx, callback_data.id, callback_data.extra or "me")


@router.message(AccountStates.target, F.text)
async def acc_set_target(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    target = (message.text or "").strip()
    if not (target.startswith("@") or target.lstrip("-").isdigit() or target.lower() == "me"):
        await message.answer("Нужен @username, числовой ID или «me».")
        return
    account_id = int((await state.get_data()).get("account_id") or 0)
    await state.clear()
    await _apply_target(message, repo, ctx, account_id, target)


# ------------------------------------------------------------------ управление


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "target")))
async def acc_target(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await state.set_state(AccountStates.target)
    await state.update_data(account_id=callback_data.id)
    await show(callback, "Новый получатель уведомлений: @username, числовой ID или «me».",
               kb(btn("Отмена", AdminCB(section=S, action="view", id=callback_data.id), icon=E.CROSS_EMOJI)))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "test")))
async def acc_test(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    account = await repo.accounts.get(callback_data.id)
    if account is None:
        return await safe_answer(callback, "Не найден", alert=True)
    await safe_answer(callback, "Отправляю тест…")
    await _apply_target(callback, repo, ctx, account.id, account.notify_target or "me")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "toggle")))
async def acc_toggle(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    account = await repo.accounts.get(callback_data.id)
    if account is None:
        return await safe_answer(callback, "Не найден", alert=True)
    account.is_active = not account.is_active
    await repo.commit()
    if not account.is_active:
        await ctx.accounts.drop_client(account.id)
    await show_account(callback, repo, ctx, account.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "del")))
async def acc_delete(callback: CallbackQuery, callback_data: AdminCB) -> None:
    await show(callback, "Отключить аккаунт? Сессия будет завершена в Telegram и удалена из базы.", confirm_kb(
        AdminCB(section=S, action="delok", id=callback_data.id), AdminCB(section=S, action="view", id=callback_data.id),
        yes_text="Да, отключить"))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "delok")))
async def acc_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, ctx: AppContext) -> None:
    account = await repo.accounts.get(callback_data.id)
    if account is not None:
        await ctx.accounts.logout(account.id, account.session_encrypted)
        await repo.accounts.delete(account)
        await repo.commit()
    await show_accounts(callback, repo, ctx)
    await safe_answer(callback, "Аккаунт отключён")
