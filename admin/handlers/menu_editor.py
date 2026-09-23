"""Настройка главного меню: тексты кнопок, стиль (цвет), иконки, порядок, ссылки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, cancel_kb, confirm_kb
from admin.services.emoji_input import HOW_TO, custom_emoji_id
from bot.callbacks import AdminCB
from bot.keyboards.common import STYLE_ORDER, STYLES, btn, kb
from bot.keyboards.main import main_menu_kb
from bot.services.content import get_text
from bot.services.render import safe_answer, show
from bot.states import MenuStates
from config import emoji as E
from database.models import MenuButton
from database.repositories import Repo
from utils.text import esc, is_valid_url, parse_buttons

router = Router(name="admin_menu_editor")
S = "menu"
KEY_TITLES = {"about": "Раздел «О нас»", "support": "Раздел «Поддержка»",
              "portfolio": "Раздел «Портфолио»", "ads": "Раздел «Реклама»", "link": "Кнопка-ссылка"}
STYLE_DOTS = {None: "⚪", "primary": "🔵", "success": "🟢", "danger": "🔴"}


async def show_menu_list(event: Message | CallbackQuery, repo: Repo) -> None:
    buttons = await repo.menu.all()
    lines = [f"{E.MENU_EMOJI} <b>Главное меню</b>\n", "Порядок и вид кнопок у пользователей:\n"]
    for b in buttons:
        state = "" if b.is_enabled else " (выкл.)"
        half = " ½" if b.row_width >= 2 else ""
        lines.append(f"{STYLE_DOTS.get(b.style, '⚪')} {esc(b.text)}{half}{state}")
    lines.append(
        "\n🔵 синяя · 🟢 зелёная · 🔴 красная · ⚪ обычная · ½ — половина ряда\n"
        "<i>Telegram поддерживает только эти стили кнопок — произвольный цвет задать нельзя.</i>"
    )
    rows = [
        btn(f"{STYLE_DOTS.get(b.style, '⚪')} {b.text}" + ("" if b.is_enabled else " · выкл."),
            AdminCB(section=S, action="view", id=b.id))
        for b in buttons
    ]
    await show(event, "\n".join(lines), kb(
        *rows,
        btn("Добавить кнопку-ссылку", AdminCB(section=S, action="newlink"), icon=E.PLUS_EMOJI),
        btn("Предпросмотр меню", AdminCB(section=S, action="preview"), icon=E.EYE_EMOJI),
        back_to_panel(),
    ))


def _button_text(b: MenuButton) -> str:
    return (
        f"{E.MENU_EMOJI} <b>{esc(b.text)}</b>\n\n"
        f"Тип: {KEY_TITLES.get(b.key, b.key)}\n"
        f"Стиль: {STYLE_DOTS.get(b.style, '⚪')} {STYLES.get(b.style, 'Обычная')}\n"
        f"Иконка (premium): {('<code>' + b.icon_emoji_id + '</code>') if b.icon_emoji_id else '—'}\n"
        f"Ширина: {'половина ряда' if b.row_width >= 2 else 'весь ряд'}\n"
        f"Показывается: {'да' if b.is_enabled else 'нет'}"
        + (f"\nСсылка: {esc(b.url)}" if b.key == "link" else "")
    )


async def show_button(event: Message | CallbackQuery, repo: Repo, button_id: int) -> None:
    b = await repo.menu.get(button_id)
    if b is None:
        await show_menu_list(event, repo)
        return
    bid = b.id
    await show(event, _button_text(b), kb(
        [
            btn("Текст", AdminCB(section=S, action="text", id=bid), icon=E.EDIT_EMOJI),
            btn("Стиль / цвет", AdminCB(section=S, action="style", id=bid), style=b.style or "primary"),
        ],
        [
            btn("Иконка", AdminCB(section=S, action="icon", id=bid), icon=E.STAR_EMOJI),
            btn("½ ряда" if b.row_width < 2 else "Весь ряд", AdminCB(section=S, action="width", id=bid)),
        ],
        btn("Изменить ссылку", AdminCB(section=S, action="url", id=bid), icon=E.LINK_EMOJI)
        if b.key == "link" else None,
        [
            btn("Выше", AdminCB(section=S, action="up", id=bid), icon=E.UP_EMOJI),
            btn("Ниже", AdminCB(section=S, action="down", id=bid), icon=E.DOWN_EMOJI),
        ],
        btn("Выключить" if b.is_enabled else "Включить", AdminCB(section=S, action="toggle", id=bid),
            icon=E.EYE_OFF_EMOJI if b.is_enabled else E.EYE_EMOJI),
        btn("Удалить", AdminCB(section=S, action="del", id=bid), icon=E.TRASH_EMOJI, style="danger")
        if b.key == "link" else None,
        back(S),
    ))


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def cb_list(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_menu_list(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "view")))
async def cb_view(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_button(callback, repo, callback_data.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "preview")))
async def cb_preview(callback: CallbackQuery, repo: Repo) -> None:
    text = await get_text(repo, "welcome_text")
    photo = await repo.settings.get("welcome_photo")
    markup = main_menu_kb(await repo.menu.all(), is_admin=False)
    if isinstance(callback.message, Message):
        if photo and len(text) <= 1024:
            await callback.message.answer_photo(photo, caption=text, reply_markup=markup)
        else:
            await callback.message.answer(text, reply_markup=markup)
    await safe_answer(callback, "Так меню видят пользователи")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "style")))
async def cb_style(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    b = await repo.menu.get(callback_data.id)
    if b is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    b.style = STYLE_ORDER[(STYLE_ORDER.index(b.style) + 1) % len(STYLE_ORDER)] if b.style in STYLE_ORDER else None
    await repo.commit()
    await show_button(callback, repo, b.id)
    await safe_answer(callback, f"Стиль: {STYLES[b.style]}")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "width")))
async def cb_width(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    b = await repo.menu.get(callback_data.id)
    if b is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    b.row_width = 1 if b.row_width >= 2 else 2
    await repo.commit()
    await show_button(callback, repo, b.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "toggle")))
async def cb_toggle(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    b = await repo.menu.get(callback_data.id)
    if b is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    await repo.menu.toggle(b)
    await repo.commit()
    await show_button(callback, repo, b.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & F.action.in_({"up", "down"})))
async def cb_move(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    await repo.menu.move(callback_data.id, -1 if callback_data.action == "up" else 1)
    await repo.commit()
    await show_menu_list(callback, repo)
    await safe_answer(callback, "Порядок изменён")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "del")))
async def cb_delete(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    b = await repo.menu.get(callback_data.id)
    if b is None or b.key != "link":
        return await safe_answer(callback, "Встроенные разделы можно только выключить", alert=True)
    await show(callback, f"Удалить кнопку «{esc(b.text)}»?", confirm_kb(
        AdminCB(section=S, action="delok", id=b.id), AdminCB(section=S, action="view", id=b.id)))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "delok")))
async def cb_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    b = await repo.menu.get(callback_data.id)
    if b is not None and b.key == "link":
        await repo.menu.delete(b)
        await repo.commit()
    await show_menu_list(callback, repo)
    await safe_answer(callback, "Удалено")


# ------------------------------------------------------------------ ввод значений


@router.callback_query(AdminCB.filter((F.section == S) & F.action.in_({"text", "icon", "url"})))
async def cb_input(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    prompts = {
        "text": (MenuStates.text, "Новый текст кнопки (до 40 символов). Эмодзи в начале можно не ставить — "
                                  "для этого есть premium-иконка."),
        "icon": (MenuStates.icon, HOW_TO),
        "url": (MenuStates.url, "Новая ссылка (https://… или tg://…):"),
    }
    new_state, prompt = prompts[callback_data.action]
    await state.set_state(new_state)
    await state.update_data(menu_button=callback_data.id)
    await show(callback, prompt, kb(btn("Отмена", AdminCB(section=S, action="view", id=callback_data.id),
                                        icon=E.CROSS_EMOJI)))
    await safe_answer(callback)


async def _target(state: FSMContext, repo: Repo) -> MenuButton | None:
    return await repo.menu.get(int((await state.get_data()).get("menu_button") or 0))


@router.message(MenuStates.text, F.text)
async def do_text(message: Message, state: FSMContext, repo: Repo) -> None:
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 40:
        await message.answer("Текст кнопки — от 1 до 40 символов.")
        return
    b = await _target(state, repo)
    await state.clear()
    if b is not None:
        b.text = text
        await repo.commit()
        await show_button(message, repo, b.id)


@router.message(MenuStates.icon)
async def do_icon(message: Message, state: FSMContext, repo: Repo) -> None:
    b = await _target(state, repo)
    if (message.text or "").strip() == "-":
        icon = None
    else:
        icon = custom_emoji_id(message)
        if icon is None:
            await message.answer("Не нашёл premium-эмодзи в сообщении. " + HOW_TO)
            return
    await state.clear()
    if b is not None:
        b.icon_emoji_id = icon
        await repo.commit()
        await show_button(message, repo, b.id)


@router.message(MenuStates.url, F.text)
async def do_url(message: Message, state: FSMContext, repo: Repo) -> None:
    url = (message.text or "").strip()
    if not is_valid_url(url):
        await message.answer("Некорректная ссылка.")
        return
    b = await _target(state, repo)
    await state.clear()
    if b is not None:
        b.url = url
        await repo.commit()
        await show_button(message, repo, b.id)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "newlink")))
async def cb_new_link(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MenuStates.new_link)
    await show(callback, "Новая кнопка-ссылка в главном меню. Формат:\n<code>Наш сайт - https://example.com</code>",
               cancel_kb(S))
    await safe_answer(callback)


@router.message(MenuStates.new_link, F.text)
async def do_new_link(message: Message, state: FSMContext, repo: Repo) -> None:
    try:
        rows = parse_buttons(message.text or "")
    except ValueError as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    first = rows[0][0]
    if len(first["text"]) > 40:
        await message.answer("Текст кнопки — до 40 символов.")
        return
    created = await repo.menu.create(key="link", text=first["text"], url=first["url"])
    await repo.commit()
    await state.clear()
    await show_button(message, repo, created.id)
