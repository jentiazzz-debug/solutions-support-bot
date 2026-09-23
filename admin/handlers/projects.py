"""Управление проектами портфолио («О нас» → «Наши проекты»)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.keyboards.panel import back, back_to_panel, cancel_kb, confirm_kb
from bot.callbacks import AdminCB
from bot.keyboards.common import btn, kb
from bot.keyboards.main import project_kb
from bot.services.content import project_card
from bot.services.render import safe_answer, show
from bot.states import ProjectStates
from config import emoji as E
from database.models import Project
from database.repositories import Repo
from utils.text import esc, fmt_number, is_valid_url, normalize_username, parse_buttons, truncate

router = Router(name="admin_projects")
S = "proj"
SKIP = "-"

FIELDS: dict[str, str] = {
    "title": "Название",
    "description": "Описание",
    "bot_username": "Username бота",
    "users_count": "Кол-во пользователей",
    "url": "Ссылка",
    "image_file_id": "Изображение",
}
PROMPTS: dict[str, str] = {
    "title": "Название проекта (до 128 символов):",
    "description": "Описание проекта (до 1500 символов):",
    "bot_username": "Username бота, например @emojimakerobot. «-» — без бота.",
    "users_count": "Количество пользователей — число, например 2000. «-» — не показывать.",
    "url": "Ссылка на проект (https://… или t.me/…). «-» — взять из username бота.",
    "image_file_id": "Отправьте изображение (фото). «-» — без изображения.",
}
WIZARD = ["title", "description", "bot_username", "users_count", "url", "image_file_id"]
STATES = {
    "title": ProjectStates.title,
    "description": ProjectStates.description,
    "bot_username": ProjectStates.username,
    "users_count": ProjectStates.users,
    "url": ProjectStates.url,
    "image_file_id": ProjectStates.image,
}


class InvalidValue(ValueError):
    pass


def parse_field(field: str, message: Message) -> object:
    """Проверить и привести значение поля. InvalidValue — с понятным текстом."""
    text = (message.text or message.caption or "").strip()
    if field == "image_file_id":
        if message.photo:
            return message.photo[-1].file_id
        if text == SKIP:
            return None
        raise InvalidValue("Нужно фото (не файлом) или «-».")
    if field == "title":
        if not text or len(text) > 128:
            raise InvalidValue("Название — от 1 до 128 символов.")
        return text
    if field == "description":
        if text == SKIP:
            return ""
        if len(text) > 1500:
            raise InvalidValue("Описание — не длиннее 1500 символов.")
        return text
    if text == SKIP:
        return None
    if field == "bot_username":
        username = normalize_username(text)
        if username is None:
            raise InvalidValue("Некорректный username. Пример: @emojimakerobot")
        return username
    if field == "users_count":
        digits = text.replace(" ", "").replace("_", "")
        if not digits.isdigit() or int(digits) > 2_000_000_000:
            raise InvalidValue("Нужно целое число, например 2000.")
        return int(digits)
    if field == "url":
        url = text if "://" in text else f"https://{text}"
        if not is_valid_url(url):
            raise InvalidValue("Некорректная ссылка.")
        return url
    raise InvalidValue("Неизвестное поле")


async def show_projects(event: Message | CallbackQuery, repo: Repo) -> None:
    projects = await repo.projects.all()
    text = f"{E.PROJECTS_EMOJI} <b>Проекты</b> · {len(projects)}\n\n" + (
        "👁 — показывается пользователям, 🙈 — скрыт.\nПорядок здесь = порядок в разделе «О нас»."
        if projects else "Проектов пока нет."
    )
    buttons = [
        btn(f"{'👁' if p.is_visible else '🙈'} {i}. {truncate(p.title, 40)}",
            AdminCB(section=S, action="view", id=p.id))
        for i, p in enumerate(projects, start=1)
    ]
    await show(event, text, kb(
        *buttons,
        btn("Добавить проект", AdminCB(section=S, action="new"), icon=E.PLUS_EMOJI, style="success"),
        back_to_panel(),
    ))


def project_admin_text(p: Project) -> str:
    links = ", ".join(esc(link.get("title", "")) for link in p.extra_links or []) or "—"
    return (
        f"{E.BOT_EMOJI} <b>{esc(p.title)}</b> · {'👁 виден' if p.is_visible else '🙈 скрыт'}\n\n"
        f"<b>Описание:</b> {esc(truncate(p.description or '—', 900))}\n"
        f"<b>Username:</b> {('@' + esc(p.bot_username)) if p.bot_username else '—'}\n"
        f"<b>Пользователей:</b> {fmt_number(p.users_count)}\n"
        f"<b>Ссылка:</b> {esc(p.url or '—')}\n"
        f"<b>Изображение:</b> {'есть' if p.image_file_id else '—'}\n"
        f"<b>Доп. ссылки:</b> {links}"
    )


def project_admin_kb(p: Project):
    pid = p.id
    field_buttons = [
        btn(title, AdminCB(section=S, action="edit", id=pid, extra=field)) for field, title in FIELDS.items()
    ]
    return kb(
        field_buttons[0:2], field_buttons[2:4], field_buttons[4:6],
        [
            btn("Добавить ссылки", AdminCB(section=S, action="links", id=pid), icon=E.LINK_EMOJI),
            btn("Очистить ссылки", AdminCB(section=S, action="clrlinks", id=pid)) if p.extra_links else None,
        ],
        [
            btn("Скрыть" if p.is_visible else "Показать", AdminCB(section=S, action="toggle", id=pid),
                icon=E.EYE_OFF_EMOJI if p.is_visible else E.EYE_EMOJI),
            btn("Предпросмотр", AdminCB(section=S, action="preview", id=pid), icon=E.EYE_EMOJI),
        ],
        [
            btn("Выше", AdminCB(section=S, action="up", id=pid), icon=E.UP_EMOJI),
            btn("Ниже", AdminCB(section=S, action="down", id=pid), icon=E.DOWN_EMOJI),
        ],
        btn("Удалить проект", AdminCB(section=S, action="del", id=pid), icon=E.TRASH_EMOJI, style="danger"),
        back(S, "К проектам"),
    )


async def show_project(event: Message | CallbackQuery, repo: Repo, project_id: int) -> None:
    project = await repo.projects.get(project_id)
    if project is None:
        await show_projects(event, repo)
        return
    await show(event, project_admin_text(project), project_admin_kb(project))


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "")))
async def cb_list(callback: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_projects(callback, repo)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "view")))
async def cb_view(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, repo: Repo) -> None:
    await state.set_state(None)
    await show_project(callback, repo, callback_data.id)
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "preview")))
async def cb_preview(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is None or not isinstance(callback.message, Message):
        await safe_answer(callback, "Не найден", alert=True)
        return
    if project.image_file_id:
        await callback.message.answer_photo(project.image_file_id, caption=project_card(project)[:1024],
                                            reply_markup=project_kb(project))
    else:
        await callback.message.answer(project_card(project), reply_markup=project_kb(project))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "toggle")))
async def cb_toggle(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is None:
        await safe_answer(callback, "Не найден", alert=True)
        return
    visible = await repo.projects.toggle(project)
    await repo.commit()
    await show_project(callback, repo, project.id)
    await safe_answer(callback, "Проект показан" if visible else "Проект скрыт")


@router.callback_query(AdminCB.filter((F.section == S) & F.action.in_({"up", "down"})))
async def cb_move(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    moved = await repo.projects.move(callback_data.id, -1 if callback_data.action == "up" else 1)
    await repo.commit()
    await show_projects(callback, repo)
    await safe_answer(callback, "Порядок изменён" if moved else "Дальше некуда")


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "del")))
async def cb_delete(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is None:
        await safe_answer(callback, "Не найден", alert=True)
        return
    await show(callback, f"Удалить проект «{esc(project.title)}»? Это нельзя отменить.", confirm_kb(
        AdminCB(section=S, action="delok", id=project.id), AdminCB(section=S, action="view", id=project.id)
    ))
    await safe_answer(callback)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "delok")))
async def cb_delete_ok(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is not None:
        await repo.projects.delete(project)
        await repo.commit()
    await show_projects(callback, repo)
    await safe_answer(callback, "Проект удалён")


# ------------------------------------------------------------------ мастер создания


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "new")))
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProjectStates.title)
    await state.update_data(project={})
    await show(callback, f"<b>Новый проект · шаг 1/6</b>\n\n{PROMPTS['title']}", cancel_kb(S))
    await safe_answer(callback)


async def _wizard_step(message: Message, state: FSMContext, repo: Repo, field: str) -> None:
    try:
        value = parse_field(field, message)
    except InvalidValue as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    data = await state.get_data()
    project: dict = data.get("project", {})
    project[field] = value
    await state.update_data(project=project)
    index = WIZARD.index(field)
    if index + 1 < len(WIZARD):
        nxt = WIZARD[index + 1]
        await state.set_state(STATES[nxt])
        await message.answer(f"<b>Новый проект · шаг {index + 2}/6</b>\n\n{PROMPTS[nxt]}",
                             reply_markup=cancel_kb(S))
        return
    if not project.get("url") and project.get("bot_username"):
        project["url"] = f"https://t.me/{project['bot_username']}"
    created = await repo.projects.create(
        title=project["title"],
        description=project.get("description") or "",
        bot_username=project.get("bot_username"),
        users_count=project.get("users_count"),
        url=project.get("url"),
        image_file_id=project.get("image_file_id"),
        extra_links=[],
    )
    await repo.commit()
    await state.clear()
    await message.answer(f"{E.CLOSE_EMOJI} Проект «{esc(created.title)}» добавлен.")
    await show_project(message, repo, created.id)


def _make_step(field: str):
    async def step(message: Message, state: FSMContext, repo: Repo) -> None:
        await _wizard_step(message, state, repo, field)

    step.__name__ = f"project_step_{field}"
    return step


for _field, _state in STATES.items():
    router.message.register(_make_step(_field), _state)


# ------------------------------------------------------------------ правка полей


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "edit")))
async def cb_edit(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    field = callback_data.extra
    if field not in FIELDS:
        await safe_answer(callback, "Неизвестное поле", alert=True)
        return
    await state.set_state(ProjectStates.edit_field)
    await state.update_data(edit_project=callback_data.id, edit_field=field)
    await show(callback, f"<b>{FIELDS[field]}</b>\n\n{PROMPTS[field]}",
               kb(btn("Отмена", AdminCB(section=S, action="view", id=callback_data.id), icon=E.CROSS_EMOJI)))
    await safe_answer(callback)


@router.message(ProjectStates.edit_field)
async def do_edit(message: Message, state: FSMContext, repo: Repo) -> None:
    data = await state.get_data()
    field = data.get("edit_field", "")
    project = await repo.projects.get(int(data.get("edit_project") or 0))
    if project is None or field not in FIELDS:
        await state.clear()
        await message.answer("Проект не найден.")
        return
    try:
        value = parse_field(field, message)
    except InvalidValue as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    if field == "url" and value is None and project.bot_username:
        value = f"https://t.me/{project.bot_username}"
    await repo.projects.update(project, **{field: value})
    await repo.commit()
    await state.clear()
    await show_project(message, repo, project.id)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "links")))
async def cb_links(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await state.set_state(ProjectStates.add_link)
    await state.update_data(edit_project=callback_data.id)
    await show(callback, (
        f"{E.LINK_EMOJI} <b>Дополнительные ссылки</b>\n\n"
        "Отправьте ссылки, по одной в строке:\n"
        "<code>Канал - https://t.me/channel</code>\n<code>Чат - https://t.me/chat</code>"
    ), kb(btn("Отмена", AdminCB(section=S, action="view", id=callback_data.id), icon=E.CROSS_EMOJI)))
    await safe_answer(callback)


@router.message(ProjectStates.add_link, F.text)
async def do_links(message: Message, state: FSMContext, repo: Repo) -> None:
    project = await repo.projects.get(int((await state.get_data()).get("edit_project") or 0))
    if project is None:
        await state.clear()
        return
    try:
        rows = parse_buttons((message.text or "").replace(" | ", "\n"))
    except ValueError as error:
        await message.answer(f"{E.WARNING_EMOJI} {error}")
        return
    links = list(project.extra_links or []) + [
        {"title": b["text"], "url": b["url"]} for row in rows for b in row
    ]
    if len(links) > 8:
        await message.answer("Не больше 8 дополнительных ссылок у проекта.")
        return
    await repo.projects.update(project, extra_links=links)
    await repo.commit()
    await state.clear()
    await show_project(message, repo, project.id)


@router.callback_query(AdminCB.filter((F.section == S) & (F.action == "clrlinks")))
async def cb_clear_links(callback: CallbackQuery, callback_data: AdminCB, repo: Repo) -> None:
    project = await repo.projects.get(callback_data.id)
    if project is not None:
        await repo.projects.update(project, extra_links=[])
        await repo.commit()
    await show_project(callback, repo, callback_data.id)
    await safe_answer(callback, "Ссылки удалены")
