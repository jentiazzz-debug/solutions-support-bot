"""Показ «экранов» интерфейса.

По нажатию inline-кнопки экран меняется в том же сообщении (без спама
новыми сообщениями). Если тип сообщения не совпадает (было фото, стало
текст) — старое удаляется и отправляется новое.
"""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024


async def show(
    event: Message | CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    photo: str | None = None,
) -> Message | None:
    if photo and len(text) > CAPTION_LIMIT:
        photo = None  # подпись к фото ограничена 1024 символами — показываем текстом

    if isinstance(event, CallbackQuery):
        message = event.message if isinstance(event.message, Message) else None
        if message is not None:
            try:
                if photo and message.photo:
                    from aiogram.types import InputMediaPhoto

                    result = await message.edit_media(
                        InputMediaPhoto(media=photo, caption=text), reply_markup=markup
                    )
                    return result if isinstance(result, Message) else message
                if not photo and message.text is not None:
                    result = await message.edit_text(
                        text, reply_markup=markup, disable_web_page_preview=True
                    )
                    return result if isinstance(result, Message) else message
            except TelegramBadRequest as error:
                if "message is not modified" in error.message:
                    return message
                log.debug("edit не удался (%s) — отправляю новое сообщение", error.message)
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return await _send(message, text, markup, photo)
        # Сообщение старше 48 ч недоступно боту — показываем экран новым сообщением.
        if event.bot is not None:
            if photo:
                try:
                    return await event.bot.send_photo(event.from_user.id, photo, caption=text, reply_markup=markup)
                except TelegramBadRequest:
                    pass
            return await event.bot.send_message(event.from_user.id, text, reply_markup=markup)
        return None
    return await _send(event, text, markup, photo)


async def _send(
    target: Message, text: str, markup: InlineKeyboardMarkup | None, photo: str | None
) -> Message:
    if photo:
        try:
            return await target.answer_photo(photo, caption=text, reply_markup=markup)
        except TelegramBadRequest as error:
            log.warning("Фото не отправилось (%s) — показываю текстом", error.message)
    return await target.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def safe_answer(callback: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=alert)
    except TelegramBadRequest:
        pass  # query устарел — не страшно
