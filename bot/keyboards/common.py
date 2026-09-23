"""Построение inline-кнопок с поддержкой стиля и premium-иконки.

Bot API 9.4+ позволяет у кнопки задать:
  • style — "primary" (синяя), "success" (зелёная), "danger" (красная);
  • icon_custom_emoji_id — кастомный эмодзи перед текстом.
Произвольный цвет (HEX) Telegram не поддерживает — только эти стили.
"""

from __future__ import annotations

from typing import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config.emoji import Emoji

STYLES: dict[str | None, str] = {
    None: "Обычная",
    "primary": "Синяя",
    "success": "Зелёная",
    "danger": "Красная",
}
STYLE_ORDER: list[str | None] = [None, "primary", "success", "danger"]


def btn(
    text: str,
    cb: CallbackData | str | None = None,
    *,
    url: str | None = None,
    icon: Emoji | str | None = None,
    style: str | None = None,
    copy_text: str | None = None,
) -> InlineKeyboardButton:
    icon_id: str | None
    if isinstance(icon, Emoji):
        icon_id = icon.custom_id
        if not icon_id:
            text = f"{icon.fallback} {text}"
    else:
        icon_id = icon
    kwargs: dict = {"text": text}
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    if style:
        kwargs["style"] = style
    if url:
        kwargs["url"] = url
    elif copy_text is not None:
        from aiogram.types import CopyTextButton

        kwargs["copy_text"] = CopyTextButton(text=copy_text[:256])
    else:
        kwargs["callback_data"] = cb.pack() if isinstance(cb, CallbackData) else (cb or "noop")
    return InlineKeyboardButton(**kwargs)


def kb(*rows: Iterable[InlineKeyboardButton] | InlineKeyboardButton | None) -> InlineKeyboardMarkup:
    """kb([b1, b2], b3, None) — ряды; одиночная кнопка = ряд из одной; None пропускается."""
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if row is None:
            continue
        if isinstance(row, InlineKeyboardButton):
            keyboard.append([row])
        else:
            items = [b for b in row if b is not None]
            if items:
                keyboard.append(items)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def chunks(items: list[InlineKeyboardButton], size: int) -> list[list[InlineKeyboardButton]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def pager(
    make_cb, page: int, total: int, per_page: int
) -> list[InlineKeyboardButton] | None:
    pages = max((total + per_page - 1) // per_page, 1)
    if pages <= 1:
        return None
    row: list[InlineKeyboardButton] = []
    row.append(btn("‹", make_cb(page - 1)) if page > 0 else btn(" ", "noop"))
    row.append(btn(f"{page + 1} / {pages}", "noop"))
    row.append(btn("›", make_cb(page + 1)) if page + 1 < pages else btn(" ", "noop"))
    return row
