"""Deep links для тикетов.

1. Ссылка на бота: https://t.me/<bot>?start=t1042 — открывает тикет #1042
   у его владельца (параметр start, официальный deep linking Bot API).
2. Ссылка для администратора: ?start=adm1042 — сразу открывает карточку
   тикета в админке (используется в уведомлениях доп. аккаунта, где
   inline-кнопок нет).
3. Ссылка в ЛС поддержки с готовым текстом: https://t.me/<username>?text=...
   Telegram подставит текст в поле ввода, но отправит его сам пользователь —
   отправить сообщение за пользователя по ссылке невозможно (и это правильно).
"""

from __future__ import annotations

from urllib.parse import quote

TICKET_PREFIX = "t"
ADMIN_PREFIX = "adm"


def bot_ticket_link(bot_username: str, ticket_id: int) -> str:
    return f"https://t.me/{bot_username}?start={TICKET_PREFIX}{ticket_id}"


def admin_ticket_link(bot_username: str, ticket_id: int) -> str:
    return f"https://t.me/{bot_username}?start={ADMIN_PREFIX}{ticket_id}"


def support_prefill_text(ticket_id: int) -> str:
    return f"Привет, я из Telegram-бота. Мне нужна помощь.\nНомер тикета: #{ticket_id}"


def support_dm_link(support_username: str, ticket_id: int) -> str | None:
    username = (support_username or "").strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}?text={quote(support_prefill_text(ticket_id))}"


def parse_start_payload(payload: str | None) -> tuple[str, int] | None:
    """'t1042' → ('ticket', 1042); 'adm1042' → ('admin', 1042)."""
    if not payload:
        return None
    for prefix, kind in ((ADMIN_PREFIX, "admin"), (TICKET_PREFIX, "ticket")):
        if payload.startswith(prefix) and payload[len(prefix):].isdigit():
            return kind, int(payload[len(prefix):])
    return None
