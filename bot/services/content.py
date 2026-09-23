"""Тексты экранов, собранные из БД."""

from __future__ import annotations

from typing import Sequence

from config import emoji as E
from database.models import Project
from database.repositories import Repo
from database.seed import ABOUT_TEXT, ADS_TEXT, PORTFOLIO_TEXT, SUPPORT_TEXT, WELCOME_TEXT
from utils.text import esc, fmt_number, truncate

MESSAGE_LIMIT = 4096

DEFAULT_TEXTS = {
    "welcome_text": WELCOME_TEXT,
    "about_text": ABOUT_TEXT,
    "support_text": SUPPORT_TEXT,
    "portfolio_text": PORTFOLIO_TEXT,
    "ads_text": ADS_TEXT,
}

TEXT_TITLES = {
    "welcome_text": "Приветствие (/start)",
    "about_text": "О нас",
    "support_text": "Поддержка",
    "portfolio_text": "Портфолио",
    "ads_text": "Реклама (цены)",
}


async def get_text(repo: Repo, key: str) -> str:
    return await repo.settings.get(key) or DEFAULT_TEXTS.get(key, "")


def project_line(index: int, project: Project, description_limit: int) -> str:
    lines = [f"<b>{index}. {esc(project.title)}</b>"]
    if project.description:
        lines.append(f"   {esc(truncate(project.description, description_limit))}")
    meta: list[str] = []
    if project.bot_username:
        meta.append(f"{E.BOT_EMOJI} @{esc(project.bot_username.lstrip('@'))}")
    if project.users_count:
        meta.append(f"{E.USERS_EMOJI} {fmt_number(project.users_count)} польз.")
    if meta:
        lines.append("   " + " · ".join(meta))
    if project.url and not (project.bot_username and project.url.rstrip("/").lower().endswith(
        project.bot_username.lstrip("@").lower()
    )):
        lines.append(f"   {E.LINK_EMOJI} {esc(project.url)}")
    for link in project.extra_links or []:
        if isinstance(link, dict) and link.get("url"):
            lines.append(f'   • <a href="{esc(link["url"])}">{esc(link.get("title") or "Ссылка")}</a>')
    return "\n".join(lines)


def projects_block(projects: Sequence[Project], budget: int) -> str:
    """Список проектов, уложенный в budget символов (урезаем описания)."""
    if not projects:
        return f"{E.PROJECTS_EMOJI} <b>Наши проекты</b>\n\nСписок проектов скоро появится."
    for limit in (220, 150, 90, 50, 0):
        body = "\n\n".join(project_line(i, p, limit) for i, p in enumerate(projects, start=1))
        text = f"{E.PROJECTS_EMOJI} <b>Наши проекты</b>\n\n{body}"
        if len(text) <= budget:
            return text
    return text[:budget]


async def about_screen(repo: Repo) -> tuple[str, Sequence[Project]]:
    about = await get_text(repo, "about_text")
    projects = await repo.projects.all(only_enabled=True)
    budget = MESSAGE_LIMIT - len(about) - 50
    return f"{about}\n\n{projects_block(projects, budget)}", projects


def project_card(project: Project) -> str:
    lines = [f"{E.BOT_EMOJI} <b>{esc(project.title)}</b>"]
    if project.description:
        lines.append(f"\n{esc(project.description)}")
    meta = []
    if project.bot_username:
        meta.append(f"Бот: @{esc(project.bot_username.lstrip('@'))}")
    if project.users_count:
        meta.append(f"Пользователей: <b>{fmt_number(project.users_count)}</b>")
    if project.url:
        meta.append(f"Ссылка: {esc(project.url)}")
    if meta:
        lines.append("\n" + "\n".join(meta))
    return "\n".join(lines)
