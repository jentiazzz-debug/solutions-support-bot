"""Фейковый Telegram Bot API: запоминает запросы и отдаёт правдоподобные ответы.

Позволяет прогнать настоящие хендлеры через Dispatcher.feed_update
без сети и без реального токена.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import (
    CopyMessage,
    EditMessageMedia,
    EditMessageText,
    GetMe,
    SendAnimation,
    SendDocument,
    SendMessage,
    SendPhoto,
    SendSticker,
    SendVideo,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    MessageEntity,
    MessageId,
    PhotoSize,
    Sticker,
    Update,
    User,
)

BOT_ID = 7000000001
_update_ids = itertools.count(1)
_callback_ids = itertools.count(1)


def now() -> datetime:
    return datetime.now(timezone.utc)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self.blocked: set[int] = set()
        self.refuse_premium = False
        self._ids: defaultdict[int, itertools.count] = defaultdict(lambda: itertools.count(100))

    # --- helpers for tests -------------------------------------------------

    def of(self, *types: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, types)]

    def to(self, chat_id: int, *types: type) -> list[Any]:
        return [r for r in self.of(*types) if getattr(r, "chat_id", None) == chat_id]

    def texts_to(self, chat_id: int) -> list[str]:
        out = []
        for r in self.requests:
            if getattr(r, "chat_id", None) == chat_id:
                value = getattr(r, "text", None) or getattr(r, "caption", None)
                if isinstance(value, str):
                    out.append(value)
        return out

    def clear(self) -> None:
        self.requests.clear()

    # --- BaseSession ----------------------------------------------------------

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    def _msg(self, chat_id: int, **fields) -> Message:
        return Message(
            message_id=next(self._ids[chat_id]),
            date=now(),
            chat=Chat(id=chat_id, type="private"),
            from_user=User(id=BOT_ID, is_bot=True, first_name="Bot", username="test_support_bot"),
            **fields,
        )

    def _has_premium(self, method: TelegramMethod) -> bool:
        for field in ("text", "caption"):
            value = getattr(method, field, None)
            if isinstance(value, str) and "<tg-emoji" in value:
                return True
        markup = getattr(method, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            for button in row:
                if getattr(button, "icon_custom_emoji_id", None):
                    return True
        return False

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.requests.append(method)
        chat_id = getattr(method, "chat_id", None)
        if isinstance(chat_id, int) and chat_id in self.blocked:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if self.refuse_premium and self._has_premium(method):
            raise TelegramBadRequest(method=method, message="Bad Request: can't use custom emoji")

        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="Bot", username="test_support_bot")
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self._ids[method.chat_id]))
        if isinstance(method, SendMessage):
            return self._msg(method.chat_id, text=method.text)
        if isinstance(method, SendPhoto):
            return self._msg(method.chat_id, caption=method.caption,
                             photo=[PhotoSize(file_id=str(method.photo), file_unique_id="u", width=1, height=1)])
        if isinstance(method, (SendVideo, SendAnimation, SendDocument)):
            return self._msg(method.chat_id, caption=method.caption)
        if isinstance(method, SendSticker):
            return self._msg(method.chat_id, sticker=Sticker(
                file_id=str(method.sticker), file_unique_id="s", type="regular", width=1, height=1,
                is_animated=False, is_video=False))
        if isinstance(method, (EditMessageText, EditMessageMedia)):
            return self._msg(method.chat_id or 0, text=getattr(method, "text", None) or "x")
        rtype = method.__returning__
        if rtype is bool:
            return True
        return True


# ------------------------------------------------------------------ апдейты


def tg_user(user_id: int, username: str | None = None, name: str = "Test") -> User:
    return User(id=user_id, is_bot=False, first_name=name, username=username)


_msg_ids: defaultdict[int, itertools.count] = defaultdict(lambda: itertools.count(1))


def message_update(
    user: User,
    text: str | None = None,
    *,
    photo: str | None = None,
    caption: str | None = None,
    sticker: str | None = None,
    reply_to: int | None = None,
    entities: list[MessageEntity] | None = None,
    media_group_id: str | None = None,
) -> Update:
    chat = Chat(id=user.id, type="private")
    fields: dict[str, Any] = {}
    if text is not None:
        fields["text"] = text
        if entities:
            fields["entities"] = entities
        elif text.startswith("/"):
            fields["entities"] = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
    if photo is not None:
        fields["photo"] = [PhotoSize(file_id=photo, file_unique_id=photo + "u", width=10, height=10)]
        if caption is not None:
            fields["caption"] = caption
    if sticker is not None:
        fields["sticker"] = Sticker(file_id=sticker, file_unique_id=sticker + "u", type="regular", width=1,
                                    height=1, is_animated=False, is_video=False, emoji="🙂")
    if reply_to is not None:
        fields["reply_to_message"] = Message(message_id=reply_to, date=now(), chat=chat,
                                             from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text="x")
    if media_group_id:
        fields["media_group_id"] = media_group_id
    message = Message(message_id=next(_msg_ids[user.id]), date=now(), chat=chat, from_user=user, **fields)
    return Update(update_id=next(_update_ids), message=message)


def callback_update(user: User, data: str, message_text: str = "screen") -> Update:
    chat = Chat(id=user.id, type="private")
    message = Message(message_id=next(_msg_ids[user.id]), date=now(), chat=chat,
                      from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"), text=message_text)
    return Update(
        update_id=next(_update_ids),
        callback_query=CallbackQuery(id=str(next(_callback_ids)), from_user=user, chat_instance="ci",
                                     message=message, data=data),
    )
