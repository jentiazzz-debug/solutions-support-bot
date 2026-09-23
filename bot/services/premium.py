"""Страховка для Premium Emoji.

Кастомные эмодзи в тексте (<tg-emoji>) и иконки кнопок
(icon_custom_emoji_id) Telegram разрешает только ботам, у которых есть
купленный на Fragment юзернейм. Если боту это недоступно, Telegram
отклоняет всё сообщение.

Эта прослойка стоит на всех запросах к Bot API: при отказе снимает
разметку/иконки и повторяет запрос с обычными эмодзи, после чего
выключает premium до перезапуска — чтобы не тратить лишний запрос на
каждое сообщение. Интерфейс не ломается ни в каком случае.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType

log = logging.getLogger(__name__)

UNTAG = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)
TEXT_FIELDS = ("text", "caption")
REFUSAL_MARKERS = ("custom emoji", "custom_emoji", "emoji_id", "tg-emoji", "document_invalid")


def strip_tags(text: str) -> str:
    return UNTAG.sub(r"\1", text)


def _put(holder: Any, field: str, value: Any) -> bool:
    try:
        setattr(holder, field, value)
        return True
    except (AttributeError, ValueError, TypeError):
        try:
            object.__setattr__(holder, field, value)
            return True
        except Exception:  # noqa: BLE001
            return False


def _holders(method: Any) -> list[Any]:
    holders = [method]
    media = getattr(method, "media", None)
    if media is not None:
        holders.extend(media if isinstance(media, list) else [media])
    return holders


def _buttons(method: Any) -> list[Any]:
    markup = getattr(method, "reply_markup", None)
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
    return [button for row in rows for button in row]


def strip_method(method: Any) -> bool:
    """Снять premium-разметку с запроса. True — было что снимать."""
    touched = False
    for holder in _holders(method):
        for field in TEXT_FIELDS:
            value = getattr(holder, field, None)
            if isinstance(value, str) and "<tg-emoji" in value:
                touched |= _put(holder, field, strip_tags(value))
    for button in _buttons(method):
        if getattr(button, "icon_custom_emoji_id", None):
            touched |= _put(button, "icon_custom_emoji_id", None)
    return touched


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        if not self.enabled:
            strip_method(method)
            return await make_request(bot, method)
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as error:
            text = str(error).lower()
            if not any(marker in text for marker in REFUSAL_MARKERS):
                raise
            if not strip_method(method):
                raise
            self.enabled = False
            log.warning(
                "Telegram не принял Premium Emoji (%s). Отключаю их до перезапуска — "
                "кастомные эмодзи доступны только ботам с юзернеймом, купленным на Fragment.",
                error.message,
            )
            return await make_request(bot, method)
