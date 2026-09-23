"""Создание рассылки: сообщение → кнопки → предпросмотр → подтверждение → отправка."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back_to_panel, cancel_kb
from admin.services.broadcast_service import buttons_markup
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.keyboards.common import btn, kb
from bot.services.render import safe_answer, show
from bot.states import BroadcastStates
from config import emoji as E
from database.models import Broadcast
from database.repositories import Repo
from support.message_service import extract
from utils.text import fmt_dt, parse_buttons

router = Router(name="admin_broadcast")
S = "bc"
STATUS = {"draft": "черновик", "running": "идёт", "done": "завершена", "cancelled": "остановлена",
          "interrupted": "прервана перезапуском"}
ALLOWED = {"text", "photo", "video", "animation", "document", "audio", "voice", "video_note", "sticker"}


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def bc_home(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await state.set_state(None)
    recent = await repo.broadcasts.recent(5)
    lines = [f"{E.BROADCAST_EMOJI} <b>Рассылка</b>\n",
             "Поддерживается: текст, фото/видео/GIF/документ с подписью, стикер, голосовое, "
             "а также inline-кнопки со ссылками (несколько кнопок и рядов).\n"]
    if ctx.broadcaster and ctx.broadcaster.running:
        lines.append(f"⏳ Сейчас идёт рассылка #{ctx.broadcaster.current_id}\n")
    if recent:
        lines.append("<b>Последние:</b>")
        for b in recent:
            lines.append(f"#{b.id} · {fmt_dt(b.created_at, ctx.settings.tz)} · {STATUS.get(b.status, b.status)} · "
                         f"✅{b.sent} ⚠️{b.failed} 🚫{b.blocked} / {b.total}")
    await show(callback, "\n".join(lines), kb(
        btn("Создать рассылку", AdminCB(section=S, action="new"), icon=E.PLUS_EMOJI, style="primary"),
        back_to_panel(),
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "new")))
async def bc_new(callback: CallbackQuery, state: FSMContext, ctx: AppContext) -> None:
    if ctx.broadcaster and ctx.broadcaster.running:
        return await safe_answer(callback, "Дождитесь окончания текущей рассылки", alert=True)
    await state.set_state(BroadcastStates.content)
    await show(callback, (
        f"{E.BROADCAST_EMOJI} <b>Новая рассылка · шаг 1/3</b>\n\n"
        "Отправьте сообщение для рассылки — так, как его должны увидеть пользователи. "
        "Форматирование и premium-эмодзи сохранятся.\n"
        "<i>Альбомы (несколько фото одним сообщением) не поддерживаются — отправьте одно медиа.</i>"
    ), cancel_kb(S))
    await safe_answer(callback)


@router.message(BroadcastStates.content)
async def bc_content(message: Message, state: FSMContext) -> None:
    content = extract(message)
    if content is None or content.content_type not in ALLOWED or message.media_group_id:
        await message.answer("Этот тип не подходит для рассылки. Отправьте текст, одно медиа или стикер.")
        return
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id,
                            bc_type=content.content_type, bc_buttons=[])
    await state.set_state(BroadcastStates.buttons)
    await message.answer(
        f"{E.BROADCAST_EMOJI} <b>Шаг 2/3 · кнопки</b>\n\n"
        "Отправьте кнопки-ссылки: одна строка — один ряд, кнопки в ряду через « | ».\n\n"
        "<code>Наш канал - https://t.me/channel | Сайт - https://example.com\n"
        "Поддержка - https://t.me/bot</code>",
        reply_markup=kb(btn("Без кнопок", AdminCB(section=S, action="nobtn"), style="primary"),
                        btn("Отмена", AdminCB(section=S), icon=E.CROSS_EMOJI)),
    )


async def _preview(bot: Bot, chat_id: int, state: FSMContext, repo: Repo) -> None:
    data = await state.get_data()
    await state.set_state(BroadcastStates.confirm)
    markup = buttons_markup(data.get("bc_buttons") or [])
    await bot.send_message(chat_id, f"{E.EYE_EMOJI} <b>Шаг 3/3 · предпросмотр</b>")
    try:
        await bot.copy_message(chat_id, data["bc_chat"], data["bc_msg"], reply_markup=markup)
    except TelegramBadRequest as error:
        await bot.send_message(chat_id, f"{E.WARNING_EMOJI} Не удалось показать предпросмотр: {error.message}")
        return
    recipients = len(await repo.users.broadcast_ids())
    await bot.send_message(
        chat_id,
        f"Получателей: <b>{recipients}</b>",
        reply_markup=kb(
            btn("Начать рассылку", AdminCB(section=S, action="ask"), icon=E.ROCKET_EMOJI, style="success"),
            btn("Изменить кнопки", AdminCB(section=S, action="rebtn"), icon=E.EDIT_EMOJI),
            btn("Отмена", AdminCB(section=S), icon=E.CROSS_EMOJI),
        ),
    )


@router.message(BroadcastStates.buttons, F.text)
async def bc_buttons(message: Message, state: FSMContext, repo: Repo, bot: Bot) -> None:
    try:
        rows = parse_buttons(message.text or "")
    except ValueError as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    await state.update_data(bc_buttons=rows)
    await _preview(bot, message.chat.id, state, repo)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "nobtn")), BroadcastStates.buttons)
async def bc_no_buttons(callback: CallbackQuery, state: FSMContext, repo: Repo, bot: Bot) -> None:
    await state.update_data(bc_buttons=[])
    await _preview(bot, callback.from_user.id, state, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "rebtn")), BroadcastStates.confirm)
async def bc_rebuttons(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastStates.buttons)
    await callback.message.answer(  # type: ignore[union-attr]
        "Отправьте кнопки заново (формат «Текст - ссылка», ряды — строками):",
        reply_markup=kb(btn("Без кнопок", AdminCB(section=S, action="nobtn")),
                        btn("Отмена", AdminCB(section=S), icon=E.CROSS_EMOJI)),
    )
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "ask")), BroadcastStates.confirm)
async def bc_ask(callback: CallbackQuery, repo: Repo) -> None:
    recipients = len(await repo.users.broadcast_ids())
    await show(callback, (
        f"{E.WARNING_EMOJI} <b>Вы уверены, что хотите начать рассылку?</b>\n\n"
        f"Получателей: <b>{recipients}</b>\nОтменить уже отправленные сообщения будет нельзя."
    ), kb([
        btn("Да, начать", AdminCB(section=S, action="go"), style="success"),
        btn("Отмена", AdminCB(section=S), icon=E.CROSS_EMOJI),
    ]))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "go")), BroadcastStates.confirm)
async def bc_go(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    if ctx.broadcaster is None:
        return await safe_answer(callback, "Сервис рассылок недоступен", alert=True)
    if ctx.broadcaster.running:
        return await safe_answer(callback, "Уже идёт другая рассылка", alert=True)
    data = await state.get_data()
    b = await repo.broadcasts.add(Broadcast(
        created_by=callback.from_user.id,
        source_chat_id=data["bc_chat"],
        source_message_id=data["bc_msg"],
        content_type=data.get("bc_type", "text"),
        buttons=data.get("bc_buttons") or [],
        status="running",
    ))
    await repo.commit()
    await state.clear()
    status = await callback.message.answer(f"{E.PROGRESS_EMOJI} Рассылка #{b.id} запускается…")  # type: ignore[union-attr]
    ctx.broadcaster.start(b.id, callback.from_user.id, status.message_id)
    await safe_answer(callback, "Рассылка запущена")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "stop")))
async def bc_stop(callback: CallbackQuery, callback_data: AdminCB, ctx: AppContext) -> None:
    if ctx.broadcaster and ctx.broadcaster.running and ctx.broadcaster.current_id == callback_data.id:
        ctx.broadcaster.cancel()
        await safe_answer(callback, "Останавливаю…")
    else:
        await safe_answer(callback, "Рассылка уже завершена", alert=True)
