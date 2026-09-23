"""Быстрые ответы: создание, изменение, переименование, удаление, порядок."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, cancel_kb, confirm_kb
from bot.callbacks import AdminCB
from bot.keyboards.common import btn, kb
from bot.services.render import safe_answer, show
from bot.states import QuickReplyStates
from config import emoji as E
from database.repositories import Repo
from support.message_service import SENDABLE_MEDIA, extract, send_stored
from utils.text import esc, truncate

router = Router(name="admin_quick_replies")
S = "qr"


async def show_quick_list(event: Message | CallbackQuery, repo: Repo) -> None:
    replies = await repo.quick_replies.all()
    text = f"{E.QUICK_EMOJI} <b>Быстрые ответы</b>\n\n"
    text += (
        "Готовые ответы отправляются пользователю в один клик из карточки тикета "
        "или командой /quick в режиме ответа."
        if replies else "Пока пусто — создайте первый ответ."
    )
    buttons = [btn(truncate(q.title, 40), AdminCB(section=S, action="view", id=q.id)) for q in replies]
    await show(event, text, kb(
        *buttons,
        btn("Создать ответ", AdminCB(section=S, action="new"), icon=E.PLUS_EMOJI, style="success"),
        back_to_panel(),
    ))


@router.message(StateFilter(None), Command("quick"))
async def cmd_quick(message: Message, repo: Repo) -> None:
    await show_quick_list(message, repo)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def cb_list(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_quick_list(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "view")))
async def cb_view(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    quick = await repo.quick_replies.get(callback_data.id)
    if quick is None:
        await safe_answer(callback, "Не найден", alert=True)
        return
    qid = quick.id
    kind = "текст" if quick.content_type == "text" else quick.content_type
    preview = esc(truncate(quick.html or "", 700)) if quick.html else "—"
    await show(callback, (
        f"{E.QUICK_EMOJI} <b>{esc(quick.title)}</b>\nТип: {kind}\n\n<b>Содержимое (HTML):</b>\n{preview}"
    ), kb(
        btn("Предпросмотр", AdminCB(section=S, action="preview", id=qid), icon=E.EYE_EMOJI),
        [
            btn("Переименовать", AdminCB(section=S, action="rename", id=qid), icon=E.EDIT_EMOJI),
            btn("Изменить текст", AdminCB(section=S, action="edit", id=qid), icon=E.EDIT_EMOJI),
        ],
        [
            btn("Выше", AdminCB(section=S, action="up", id=qid), icon=E.UP_EMOJI),
            btn("Ниже", AdminCB(section=S, action="down", id=qid), icon=E.DOWN_EMOJI),
        ],
        btn("Удалить", AdminCB(section=S, action="del", id=qid), icon=E.TRASH_EMOJI, style="danger"),
        back(S),
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "preview")))
async def cb_preview(callback: CallbackQuery, callback_data: AdminCB, repo: Repo, bot: Bot) -> None:
    quick = await repo.quick_replies.get(callback_data.id)
    if quick is None:
        await safe_answer(callback, "Не найден", alert=True)
        return
    await send_stored(bot, callback.from_user.id, quick.content_type, quick.html, quick.file_id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & F.action.in_({"up", "down"})))
async def cb_move(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    await repo.quick_replies.move(callback_data.id, -1 if callback_data.action == "up" else 1)
    await repo.commit()
    await show_quick_list(callback, repo)
    await safe_answer(callback, "Порядок изменён")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "del")))
async def cb_delete(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    quick = await repo.quick_replies.get(callback_data.id)
    if quick is None:
        await safe_answer(callback, "Не найден", alert=True)
        return
    await show(callback, f"Удалить быстрый ответ «{esc(quick.title)}»?", confirm_kb(
        AdminCB(section=S, action="delok", id=quick.id), AdminCB(section=S, action="view", id=quick.id)
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "delok")))
async def cb_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    quick = await repo.quick_replies.get(callback_data.id)
    if quick is not None:
        await repo.quick_replies.delete(quick)
        await repo.commit()
    await show_quick_list(callback, repo)
    await safe_answer(callback, "Удалено")


# ------------------------------------------------------------------ создание / правка


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "new")))
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuickReplyStates.title)
    await show(callback, "Название быстрого ответа (видно только админам), до 64 символов:", cancel_kb(S))
    await safe_answer(callback)


@router.message(QuickReplyStates.title, F.text)
async def new_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > 64:
        await message.answer("Название — от 1 до 64 символов.")
        return
    await state.update_data(qr_title=title)
    await state.set_state(QuickReplyStates.content)
    await message.answer(
        "Теперь отправьте сам ответ — текст (форматирование и premium-эмодзи сохранятся), "
        "фото/видео/GIF/документ с подписью или стикер.",
        reply_markup=cancel_kb(S),
    )


def _content_fields(message: Message) -> dict | None:
    content = extract(message)
    if content is None or (content.content_type != "text" and content.content_type not in SENDABLE_MEDIA):
        return None
    return {"content_type": content.content_type, "html": content.html, "file_id": content.file_id}


@router.message(QuickReplyStates.content)
async def new_content(message: Message, state: FSMContext, repo: Repo) -> None:
    fields = _content_fields(message)
    if fields is None:
        await message.answer("Этот тип сообщения не подходит. Отправьте текст, медиа или стикер.")
        return
    data = await state.get_data()
    await repo.quick_replies.create(title=data["qr_title"], **fields)
    await repo.commit()
    await state.clear()
    await message.answer(f"{E.CLOSE_EMOJI} Быстрый ответ «{esc(data['qr_title'])}» сохранён.")
    await show_quick_list(message, repo)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "rename")))
async def cb_rename(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await state.set_state(QuickReplyStates.rename)
    await state.update_data(qr_id=callback_data.id)
    await show(callback, "Новое название (до 64 символов):", cancel_kb(S))
    await safe_answer(callback)


@router.message(QuickReplyStates.rename, F.text)
async def do_rename(message: Message, state: FSMContext, repo: Repo) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > 64:
        await message.answer("Название — от 1 до 64 символов.")
        return
    quick = await repo.quick_replies.get(int((await state.get_data()).get("qr_id") or 0))
    await state.clear()
    if quick is not None:
        await repo.quick_replies.update(quick, title=title)
        await repo.commit()
    await show_quick_list(message, repo)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "edit")))
async def cb_edit(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await state.set_state(QuickReplyStates.edit_content)
    await state.update_data(qr_id=callback_data.id)
    await show(callback, "Отправьте новое содержимое ответа (текст, медиа или стикер):", cancel_kb(S))
    await safe_answer(callback)


@router.message(QuickReplyStates.edit_content)
async def do_edit(message: Message, state: FSMContext, repo: Repo) -> None:
    fields = _content_fields(message)
    if fields is None:
        await message.answer("Этот тип сообщения не подходит.")
        return
    quick = await repo.quick_replies.get(int((await state.get_data()).get("qr_id") or 0))
    await state.clear()
    if quick is not None:
        await repo.quick_replies.update(quick, **fields)
        await repo.commit()
    await message.answer(f"{E.CLOSE_EMOJI} Сохранено.")
    await show_quick_list(message, repo)
