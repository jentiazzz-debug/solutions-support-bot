"""Тексты разделов, ссылки портфолио, категории обращений, общие настройки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, cancel_kb, confirm_kb
from admin.services.emoji_input import HOW_TO, custom_emoji_id
from bot.callbacks import AdminCB
from bot.context import AppContext
from bot.keyboards.common import STYLE_ORDER, STYLES, btn, kb
from bot.services.content import DEFAULT_TEXTS, TEXT_TITLES, get_text
from bot.services.render import safe_answer, show
from bot.states import CategoryStates, LinkStates, SettingsStates
from config import emoji as E
from database.repositories import Repo
from utils.text import esc, is_valid_url, normalize_username, parse_buttons

router = Router(name="admin_content")
STYLE_DOTS = {None: "⚪", "primary": "🔵", "success": "🟢", "danger": "🔴"}

# =================================================================== ТЕКСТЫ

T = "texts"


@router.callback_query(AdminCB.filter((F.section == T) & (F.action == "")))
async def texts_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await show(callback, (
        f"{E.EDIT_EMOJI} <b>Тексты разделов</b>\n\n"
        "Отправляйте текст с обычным форматированием Telegram — жирный, курсив, ссылки и "
        "premium-эмодзи сохранятся как есть."
    ), kb(
        *[btn(title, AdminCB(section=T, action="view", extra=key)) for key, title in TEXT_TITLES.items()],
        back_to_panel(),
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == T) & (F.action == "view")))
async def text_view(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    key = callback_data.extra
    if key not in TEXT_TITLES:
        return await safe_answer(callback, "Неизвестный текст", alert=True)
    current = await get_text(repo, key)
    await show(callback, current, kb(
        btn("Изменить", AdminCB(section=T, action="edit", extra=key), icon=E.EDIT_EMOJI, style="primary"),
        btn("Вернуть исходный", AdminCB(section=T, action="reset", extra=key)),
        back(T),
    ))
    await safe_answer(callback, TEXT_TITLES[key])


@router.callback_query(AdminCB.filter((F.section == T) & (F.action == "reset")))
async def text_reset(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    key = callback_data.extra
    if key in DEFAULT_TEXTS:
        await repo.settings.set(key, DEFAULT_TEXTS[key])
        await repo.commit()
    await text_view(callback, callback_data, repo)


@router.callback_query(AdminCB.filter((F.section == T) & (F.action == "edit")))
async def text_edit(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    if callback_data.extra not in TEXT_TITLES:
        return await safe_answer(callback, "Неизвестный текст", alert=True)
    await state.set_state(SettingsStates.text)
    await state.update_data(text_key=callback_data.extra)
    await show(callback, f"Отправьте новый текст для «{TEXT_TITLES[callback_data.extra]}» (до 3500 символов).",
               kb(btn("Отмена", AdminCB(section=T, action="view", extra=callback_data.extra), icon=E.CROSS_EMOJI)))
    await safe_answer(callback)


@router.message(SettingsStates.text, F.text)
async def text_save(message: Message, state: FSMContext, repo: Repo) -> None:
    key = (await state.get_data()).get("text_key")
    if key not in TEXT_TITLES:
        await state.clear()
        return
    html = message.html_text
    if len(html) > 3500:
        await message.answer("Слишком длинно — до 3500 символов с учётом разметки.")
        return
    await repo.settings.set(key, html)
    await repo.commit()
    await state.clear()
    await message.answer(f"{E.CLOSE_EMOJI} Текст «{TEXT_TITLES[key]}» сохранён. Так он выглядит:")
    await message.answer(html, reply_markup=kb(back(T, "К текстам")))


# =================================================================== ССЫЛКИ ПОРТФОЛИО

L = "links"


async def show_links(event: Message | CallbackQuery, repo: Repo) -> None:
    links = await repo.links.all()
    await show(event, (
        f"{E.PORTFOLIO_EMOJI} <b>Раздел «Наше портфолио»</b>\n\n"
        "Кнопки-ссылки раздела (сайт, канал и любые другие). Текст раздела — в «Тексты»."
    ), kb(
        *[btn(f"{STYLE_DOTS.get(link.style, '⚪')} {link.title}" + ("" if link.is_enabled else " · выкл."),
              AdminCB(section=L, action="view", id=link.id)) for link in links],
        btn("Добавить ссылку", AdminCB(section=L, action="new"), icon=E.PLUS_EMOJI, style="success"),
        back_to_panel(),
    ))


async def show_link(event: Message | CallbackQuery, repo: Repo, link_id: int) -> None:
    link = await repo.links.get(link_id)
    if link is None:
        return await show_links(event, repo)
    lid = link.id
    await show(event, (
        f"{E.LINK_EMOJI} <b>{esc(link.title)}</b>\n\n"
        f"Ссылка: {esc(link.url)}\n"
        f"Стиль: {STYLE_DOTS.get(link.style, '⚪')} {STYLES.get(link.style, 'Обычная')}\n"
        f"Иконка: {('<code>' + link.icon_emoji_id + '</code>') if link.icon_emoji_id else '—'}\n"
        f"Показывается: {'да' if link.is_enabled else 'нет'}"
    ), kb(
        [btn("Название", AdminCB(section=L, action="title", id=lid), icon=E.EDIT_EMOJI),
         btn("Ссылка", AdminCB(section=L, action="url", id=lid), icon=E.LINK_EMOJI)],
        [btn("Стиль / цвет", AdminCB(section=L, action="style", id=lid), style=link.style or "primary"),
         btn("Иконка", AdminCB(section=L, action="icon", id=lid), icon=E.STAR_EMOJI)],
        [btn("Выше", AdminCB(section=L, action="up", id=lid), icon=E.UP_EMOJI),
         btn("Ниже", AdminCB(section=L, action="down", id=lid), icon=E.DOWN_EMOJI)],
        btn("Выключить" if link.is_enabled else "Включить", AdminCB(section=L, action="toggle", id=lid)),
        btn("Удалить", AdminCB(section=L, action="del", id=lid), icon=E.TRASH_EMOJI, style="danger"),
        back(L),
    ))


@router.callback_query(AdminCB.filter((F.section == L) & (F.action == "")))
async def links_list(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_links(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == L) & (F.action == "view")))
async def link_view(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_link(callback, repo, callback_data.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == L) & F.action.in_({"style", "toggle", "up", "down"})))
async def link_quick_actions(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    link = await repo.links.get(callback_data.id)
    if link is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    if callback_data.action == "style":
        link.style = STYLE_ORDER[(STYLE_ORDER.index(link.style) + 1) % len(STYLE_ORDER)] \
            if link.style in STYLE_ORDER else None
    elif callback_data.action == "toggle":
        await repo.links.toggle(link)
    else:
        await repo.links.move(link.id, -1 if callback_data.action == "up" else 1)
    await repo.commit()
    if callback_data.action in {"up", "down"}:
        await show_links(callback, repo)
    else:
        await show_link(callback, repo, link.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == L) & (F.action == "del")))
async def link_delete(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    link = await repo.links.get(callback_data.id)
    if link is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    await show(callback, f"Удалить ссылку «{esc(link.title)}»?", confirm_kb(
        AdminCB(section=L, action="delok", id=link.id), AdminCB(section=L, action="view", id=link.id)))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == L) & (F.action == "delok")))
async def link_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    link = await repo.links.get(callback_data.id)
    if link is not None:
        await repo.links.delete(link)
        await repo.commit()
    await show_links(callback, repo)
    await safe_answer(callback, "Удалено")


@router.callback_query(AdminCB.filter((F.section == L) & F.action.in_({"new", "title", "url", "icon"})))
async def link_input(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    prompts = {
        "new": (LinkStates.create, "Новая ссылка. Формат:\n<code>Сайт с портфолио - https://example.com</code>"),
        "title": (LinkStates.edit_title, "Новое название кнопки (до 40 символов):"),
        "url": (LinkStates.edit_url, "Новая ссылка (https://…):"),
        "icon": (LinkStates.icon, HOW_TO),
    }
    new_state, prompt = prompts[callback_data.action]
    await state.set_state(new_state)
    await state.update_data(link_id=callback_data.id)
    await show(callback, prompt, cancel_kb(L))
    await safe_answer(callback)


@router.message(LinkStates.create, F.text)
async def link_create(message: Message, state: FSMContext, repo: Repo) -> None:
    try:
        rows = parse_buttons(message.text or "")
    except ValueError as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    created = None
    for row in rows:
        for item in row:
            created = await repo.links.create(title=item["text"][:64], url=item["url"])
    await repo.commit()
    await state.clear()
    if created is not None:
        await show_link(message, repo, created.id)


@router.message(LinkStates.edit_title, F.text)
async def link_title(message: Message, state: FSMContext, repo: Repo) -> None:
    title = (message.text or "").strip()
    if not 1 <= len(title) <= 40:
        await message.answer("Название — от 1 до 40 символов.")
        return
    link = await repo.links.get(int((await state.get_data()).get("link_id") or 0))
    await state.clear()
    if link is not None:
        link.title = title
        await repo.commit()
        await show_link(message, repo, link.id)


@router.message(LinkStates.edit_url, F.text)
async def link_url(message: Message, state: FSMContext, repo: Repo) -> None:
    url = (message.text or "").strip()
    if not is_valid_url(url):
        await message.answer("Некорректная ссылка.")
        return
    link = await repo.links.get(int((await state.get_data()).get("link_id") or 0))
    await state.clear()
    if link is not None:
        link.url = url
        await repo.commit()
        await show_link(message, repo, link.id)


@router.message(LinkStates.icon)
async def link_icon(message: Message, state: FSMContext, repo: Repo) -> None:
    if (message.text or "").strip() == "-":
        icon = None
    else:
        icon = custom_emoji_id(message)
        if icon is None:
            await message.answer("Не нашёл premium-эмодзи. " + HOW_TO)
            return
    link = await repo.links.get(int((await state.get_data()).get("link_id") or 0))
    await state.clear()
    if link is not None:
        link.icon_emoji_id = icon
        await repo.commit()
        await show_link(message, repo, link.id)


# =================================================================== КАТЕГОРИИ

C = "cats"


async def show_categories(event: Message | CallbackQuery, repo: Repo) -> None:
    cats = await repo.categories.all()
    await show(event, (
        f"{E.CATEGORY_EMOJI} <b>Категории обращений</b>\n\n"
        "Пользователь выбирает тему перед созданием тикета."
    ), kb(
        *[btn(c.label + ("" if c.is_enabled else " · выкл."), AdminCB(section=C, action="view", id=c.id))
          for c in cats],
        btn("Добавить категорию", AdminCB(section=C, action="new"), icon=E.PLUS_EMOJI, style="success"),
        back_to_panel(),
    ))


async def show_category(event: Message | CallbackQuery, repo: Repo, cat_id: int) -> None:
    cat = await repo.categories.get(cat_id)
    if cat is None:
        return await show_categories(event, repo)
    cid = cat.id
    await show(event, f"{E.CATEGORY_EMOJI} <b>{esc(cat.label)}</b>\nВключена: {'да' if cat.is_enabled else 'нет'}", kb(
        btn("Переименовать", AdminCB(section=C, action="rename", id=cid), icon=E.EDIT_EMOJI),
        [btn("Выше", AdminCB(section=C, action="up", id=cid), icon=E.UP_EMOJI),
         btn("Ниже", AdminCB(section=C, action="down", id=cid), icon=E.DOWN_EMOJI)],
        btn("Выключить" if cat.is_enabled else "Включить", AdminCB(section=C, action="toggle", id=cid)),
        btn("Удалить", AdminCB(section=C, action="del", id=cid), icon=E.TRASH_EMOJI, style="danger"),
        back(C),
    ))


def parse_category(text: str) -> tuple[str, str]:
    """«🐞 Ошибка» → ("🐞", "Ошибка"). Эмодзи в начале — необязателен."""
    text = text.strip()
    first, _, rest = text.partition(" ")
    if rest and not any(ch.isalnum() for ch in first):
        return first[:8], rest.strip()[:64]
    return "", text[:64]


@router.callback_query(AdminCB.filter((F.section == C) & (F.action == "")))
async def cats_list(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_categories(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == C) & (F.action == "view")))
async def cat_view(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_category(callback, repo, callback_data.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == C) & F.action.in_({"toggle", "up", "down"})))
async def cat_quick(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    cat = await repo.categories.get(callback_data.id)
    if cat is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    if callback_data.action == "toggle":
        await repo.categories.toggle(cat)
        await repo.commit()
        await show_category(callback, repo, cat.id)
    else:
        await repo.categories.move(cat.id, -1 if callback_data.action == "up" else 1)
        await repo.commit()
        await show_categories(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == C) & (F.action == "del")))
async def cat_delete(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    cat = await repo.categories.get(callback_data.id)
    if cat is None:
        return await safe_answer(callback, "Не найдено", alert=True)
    await show(callback, f"Удалить категорию «{esc(cat.label)}»? Существующие тикеты сохранятся.", confirm_kb(
        AdminCB(section=C, action="delok", id=cat.id), AdminCB(section=C, action="view", id=cat.id)))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == C) & (F.action == "delok")))
async def cat_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    cat = await repo.categories.get(callback_data.id)
    if cat is not None:
        await repo.categories.delete(cat)
        await repo.commit()
    await show_categories(callback, repo)
    await safe_answer(callback, "Удалено")


@router.callback_query(AdminCB.filter((F.section == C) & F.action.in_({"new", "rename"})))
async def cat_input(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await state.set_state(CategoryStates.create if callback_data.action == "new" else CategoryStates.rename)
    await state.update_data(cat_id=callback_data.id)
    await show(callback, "Название категории, можно с эмодзи в начале:\n<code>🐞 Ошибка</code>", cancel_kb(C))
    await safe_answer(callback)


@router.message(CategoryStates.create, F.text)
async def cat_create(message: Message, state: FSMContext, repo: Repo) -> None:
    emoji, title = parse_category(message.text or "")
    if not title:
        await message.answer("Нужно название.")
        return
    created = await repo.categories.create(title=title, emoji=emoji)
    await repo.commit()
    await state.clear()
    await show_category(message, repo, created.id)


@router.message(CategoryStates.rename, F.text)
async def cat_rename(message: Message, state: FSMContext, repo: Repo) -> None:
    emoji, title = parse_category(message.text or "")
    cat = await repo.categories.get(int((await state.get_data()).get("cat_id") or 0))
    await state.clear()
    if cat is not None and title:
        cat.title, cat.emoji = title, emoji
        await repo.commit()
        await show_category(message, repo, cat.id)


# =================================================================== НАСТРОЙКИ

ST = "set"


async def show_settings(event: Message | CallbackQuery, repo: Repo, ctx: AppContext) -> None:
    username = await repo.settings.get("support_username") or ""
    max_raw = await repo.settings.get("max_tickets")
    max_tickets = int(max_raw) if max_raw and max_raw.isdigit() else ctx.settings.support_max_tickets
    photo = await repo.settings.get("welcome_photo")
    sticker = await repo.settings.get("welcome_sticker")
    await show(event, (
        f"{E.SETTINGS_EMOJI} <b>Настройки</b>\n\n"
        f"Username поддержки (ссылка «в ЛС»): {('@' + esc(username)) if username else '—'}\n"
        f"Лимит активных тикетов на пользователя: <b>{max_tickets}</b>\n"
        f"Фото приветствия: {'есть' if photo else '—'}\n"
        f"Стикер приветствия: {'есть' if sticker else '—'}\n"
        f"Premium Emoji: {'включены' if ctx.settings.premium_emoji_enabled else 'выключены'} (PREMIUM_EMOJI_ENABLED)"
    ), kb(
        btn("Username поддержки", AdminCB(section=ST, action="username"), icon=E.USER_EMOJI),
        btn("Лимит тикетов", AdminCB(section=ST, action="limit"), icon=E.TICKET_EMOJI),
        [btn("Фото приветствия", AdminCB(section=ST, action="photo"), icon=E.EYE_EMOJI),
         btn("Стикер приветствия", AdminCB(section=ST, action="sticker"), icon=E.STAR_EMOJI)],
        back_to_panel(),
    ))


@router.callback_query(AdminCB.filter((F.section == ST) & (F.action == "")))
async def settings_home(callback: CallbackQuery, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    await state.set_state(None)
    await show_settings(callback, repo, ctx)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == ST) & F.action.in_({"username", "limit", "photo", "sticker"})))
async def settings_input(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    prompts = {
        "username": (SettingsStates.value, "Username аккаунта поддержки, например @nudick. «-» — убрать."),
        "limit": (SettingsStates.value, "Максимум одновременно открытых тикетов у пользователя (1–50):"),
        "photo": (SettingsStates.media, "Отправьте фото для приветствия. «-» — убрать фото."),
        "sticker": (SettingsStates.media, "Отправьте стикер, который бот пришлёт перед приветствием. «-» — убрать."),
    }
    new_state, prompt = prompts[callback_data.action]
    await state.set_state(new_state)
    await state.update_data(setting=callback_data.action)
    await show(callback, prompt, cancel_kb(ST))
    await safe_answer(callback)


@router.message(SettingsStates.value, F.text)
async def settings_value(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    key = (await state.get_data()).get("setting")
    text = (message.text or "").strip()
    if key == "username":
        if text == "-":
            await repo.settings.set("support_username", "")
        else:
            username = normalize_username(text)
            if username is None:
                await message.answer("Некорректный username.")
                return
            await repo.settings.set("support_username", username)
    elif key == "limit":
        if not text.isdigit() or not 1 <= int(text) <= 50:
            await message.answer("Нужно число от 1 до 50.")
            return
        await repo.settings.set("max_tickets", text)
    await repo.commit()
    await state.clear()
    await show_settings(message, repo, ctx)


@router.message(SettingsStates.media)
async def settings_media(message: Message, state: FSMContext, repo: Repo, ctx: AppContext) -> None:
    key = (await state.get_data()).get("setting")
    remove = (message.text or "").strip() == "-"
    if key == "photo":
        if not remove and not message.photo:
            await message.answer("Нужно фото (не файлом) или «-».")
            return
        await repo.settings.set("welcome_photo", None if remove else message.photo[-1].file_id)  # type: ignore[index]
    elif key == "sticker":
        if not remove and not message.sticker:
            await message.answer("Нужен стикер или «-».")
            return
        await repo.settings.set("welcome_sticker", None if remove else message.sticker.file_id)  # type: ignore[union-attr]
    await repo.commit()
    await state.clear()
    await message.answer(f"{E.CLOSE_EMOJI} Сохранено. Проверьте: /start")
    await show_settings(message, repo, ctx)

