"""Извлечь id кастомного (premium) эмодзи из сообщения администратора."""

from __future__ import annotations

from aiogram.types import Message


def custom_emoji_id(message: Message) -> str | None:
    """Premium-эмодзи в тексте, стикер из набора эмодзи или просто числовой id."""
    for entity in message.entities or message.caption_entities or []:
        if entity.type == "custom_emoji" and entity.custom_emoji_id:
            return entity.custom_emoji_id
    if message.sticker and message.sticker.custom_emoji_id:
        return message.sticker.custom_emoji_id
    text = (message.text or "").strip()
    if text.isdigit() and 10 <= len(text) <= 25:
        return text
    return None


HOW_TO = (
    "Отправьте premium-эмодзи (просто вставьте его в сообщение), "
    "или его числовой id. «-» — убрать иконку.\n\n"
    "<i>Иконки на кнопках Telegram показывает только если у бота есть "
    "юзернейм, купленный на Fragment. Иначе бот сам покажет кнопку без иконки.</i>"
)
