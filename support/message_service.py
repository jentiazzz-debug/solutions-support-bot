"""Работа с сообщениями любых типов: разбор, пересылка, повторная отправка.

Пересылка между пользователем и администратором идёт через copyMessage:
получатель видит «чистое» сообщение (без «Переслано от»), при этом
сохраняются медиа, подписи, форматирование и кастомные эмодзи.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, Message, MessageEntity, MessageId

from utils.text import truncate

log = logging.getLogger(__name__)

T = TypeVar("T")

# content_type → (подпись в истории, есть ли файл)
CONTENT_LABELS: dict[str, str] = {
    "text": "",
    "photo": "🖼 Фото",
    "video": "🎬 Видео",
    "animation": "🎞 GIF",
    "document": "📎 Документ",
    "sticker": "🏷 Стикер",
    "voice": "🎙 Голосовое",
    "audio": "🎵 Аудио",
    "video_note": "⏺ Видеосообщение",
    "location": "📍 Геопозиция",
    "venue": "📍 Место",
    "contact": "👤 Контакт",
    "poll": "📊 Опрос",
    "dice": "🎲 Кубик",
}

# Типы, которые можно отправить повторно по file_id.
SENDABLE_MEDIA = {"photo", "video", "animation", "document", "sticker", "voice", "audio", "video_note"}


@dataclass(slots=True)
class Content:
    content_type: str
    text: str | None = None  # plain
    html: str | None = None
    file_id: str | None = None

    @property
    def label(self) -> str:
        return CONTENT_LABELS.get(self.content_type, "📦 Сообщение")

    def preview(self, limit: int = 120) -> str:
        parts = [p for p in (self.label, self.text) if p]
        return truncate(" ".join(parts) if parts else "—", limit)


def extract(message: Message) -> Content | None:
    """Разобрать сообщение. None — тип, который не пересылаем (служебные и т.п.)."""
    ctype = message.content_type
    ctype = ctype.value if hasattr(ctype, "value") else str(ctype)
    file_id: str | None = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.animation:  # до document: у GIF заполнены оба поля
        file_id = message.animation.file_id
        ctype = "animation"
    elif message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.sticker:
        file_id = message.sticker.file_id
    elif message.voice:
        file_id = message.voice.file_id
    elif message.audio:
        file_id = message.audio.file_id
    elif message.video_note:
        file_id = message.video_note.file_id

    if ctype not in CONTENT_LABELS:
        return None

    text: str | None = None
    html_text: str | None = None
    if message.text is not None:
        text, html_text = message.text, message.html_text
    elif message.caption is not None:
        text, html_text = message.caption, message.html_text
    elif message.sticker and message.sticker.emoji:
        text = message.sticker.emoji
    elif message.location:
        text = f"{message.location.latitude:.5f}, {message.location.longitude:.5f}"
    elif message.contact:
        text = f"{message.contact.first_name} {message.contact.phone_number}"
    elif message.poll:
        text = message.poll.question
    elif message.dice:
        text = f"{message.dice.emoji} {message.dice.value}"
    return Content(content_type=ctype, text=text, html=html_text, file_id=file_id)


async def with_retry(call: Callable[[], Awaitable[T]], attempts: int = 3) -> T:
    """Повторить вызов при TelegramRetryAfter (флуд-контроль)."""
    for attempt in range(attempts):
        try:
            return await call()
        except TelegramRetryAfter as error:
            if attempt == attempts - 1:
                raise
            log.warning("Flood control: ждём %s c", error.retry_after)
            await asyncio.sleep(error.retry_after + 0.5)
    raise RuntimeError("unreachable")


def _without_custom_emoji(entities: list[MessageEntity] | None) -> list[MessageEntity] | None:
    if not entities:
        return entities
    return [e for e in entities if e.type != "custom_emoji"]


async def relay(
    bot: Bot,
    message: Message,
    chat_id: int,
    reply_markup: InlineKeyboardMarkup | None = None,
    reply_to_message_id: int | None = None,
) -> int:
    """Скопировать сообщение в chat_id. Возвращает id нового сообщения.

    Если Telegram не принял копию целиком (например, из-за кастомных
    эмодзи, недоступных боту), отправляем без них — сообщение не теряется.
    """
    kwargs: dict[str, Any] = {"reply_markup": reply_markup}
    if reply_to_message_id:
        kwargs["reply_to_message_id"] = reply_to_message_id
        kwargs["allow_sending_without_reply"] = True
    try:
        result: MessageId = await with_retry(
            lambda: bot.copy_message(chat_id, message.chat.id, message.message_id, **kwargs)
        )
        return result.message_id
    except TelegramBadRequest as error:
        log.info("copyMessage не прошёл (%s), пробуем без кастомных эмодзи", error.message)

    kwargs.pop("allow_sending_without_reply", None)
    if message.text is not None:
        sent = await with_retry(
            lambda: bot.send_message(
                chat_id,
                message.text or "",
                entities=_without_custom_emoji(message.entities),
                parse_mode=None,
                **kwargs,
            )
        )
        return sent.message_id
    if message.caption is not None:
        result = await with_retry(
            lambda: bot.copy_message(
                chat_id,
                message.chat.id,
                message.message_id,
                caption=message.caption,
                caption_entities=_without_custom_emoji(message.caption_entities),
                parse_mode=None,
                **kwargs,
            )
        )
        return result.message_id
    raise TelegramBadRequest(method=None, message="Не удалось переслать сообщение")  # type: ignore[arg-type]


async def send_stored(
    bot: Bot,
    chat_id: int,
    content_type: str,
    html: str | None,
    file_id: str | None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Отправить сохранённое в БД сообщение (быстрый ответ, медиа из истории)."""
    caption = html or None
    if content_type == "text" or not file_id:
        return await with_retry(
            lambda: bot.send_message(chat_id, html or "—", reply_markup=reply_markup)
        )
    senders: dict[str, Callable[[], Awaitable[Message]]] = {
        "photo": lambda: bot.send_photo(chat_id, file_id, caption=caption, reply_markup=reply_markup),
        "video": lambda: bot.send_video(chat_id, file_id, caption=caption, reply_markup=reply_markup),
        "animation": lambda: bot.send_animation(
            chat_id, file_id, caption=caption, reply_markup=reply_markup
        ),
        "document": lambda: bot.send_document(
            chat_id, file_id, caption=caption, reply_markup=reply_markup
        ),
        "audio": lambda: bot.send_audio(chat_id, file_id, caption=caption, reply_markup=reply_markup),
        "voice": lambda: bot.send_voice(chat_id, file_id, caption=caption, reply_markup=reply_markup),
        "sticker": lambda: bot.send_sticker(chat_id, file_id, reply_markup=reply_markup),
        "video_note": lambda: bot.send_video_note(chat_id, file_id, reply_markup=reply_markup),
    }
    sender = senders.get(content_type)
    if sender is None:
        return await with_retry(
            lambda: bot.send_message(chat_id, html or "—", reply_markup=reply_markup)
        )
    return await with_retry(sender)
