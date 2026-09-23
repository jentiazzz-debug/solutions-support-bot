"""Сквозные сценарии: реальные хендлеры + SQLite + фейковый Bot API."""

from __future__ import annotations

import asyncio

import pytest
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    EditMessageText,
    SendMessage,
    SendPhoto,
)
from aiogram.types import MessageEntity

from bot.callbacks import AdminCB, MenuCB, ProjectCB, SupportCB, TicketCB
from database.models import TicketStatus
from database.repositories import Repo
from tests.conftest import OWNER_ID
from tests.fakes import callback_update, message_update, tg_user

pytestmark = pytest.mark.asyncio

OWNER = tg_user(OWNER_ID, "owner", "Owner")


async def feed(app, update) -> None:
    await app.dp.feed_update(app.bot, update)


async def repo_call(app, fn):
    async with app.ctx.db.session() as session:
        return await fn(Repo(session))


def buttons(method) -> list[list[str]]:
    markup = getattr(method, "reply_markup", None)
    return [[b.text for b in row] for row in (getattr(markup, "inline_keyboard", None) or [])]


def all_texts(app, chat_id: int) -> str:
    return "\n".join(app.session.texts_to(chat_id))


async def create_ticket(app, user, text="Помогите, бот не работает", category_index=1) -> int:
    cats = await repo_call(app, lambda r: r.categories.all(only_enabled=True))
    await feed(app, callback_update(user, SupportCB(action="new").pack()))
    await feed(app, callback_update(user, SupportCB(action="cat", id=cats[category_index].id).pack()))
    await feed(app, message_update(user, text))
    tickets = await repo_call(app, lambda r: r.tickets.active_for_user(user.id))
    return max(t.id for t in tickets)


# ------------------------------------------------------------------ меню и контент


async def test_start_main_menu_layout(app):
    user = tg_user(2001, "alice")
    await feed(app, message_update(user, "/start"))
    sent = app.session.to(user.id, SendMessage)
    assert sent, "бот должен ответить на /start"
    rows = buttons(sent[-1])
    assert rows[0] == ["О нас"]
    assert rows[1] == ["Реклама", "Наше портфолио"], "второй ряд — «Реклама» и «Наше портфолио» вместе"
    assert rows[2] == ["Поддержка"]
    assert not any("Админ" in b for row in rows for b in row), "обычный пользователь не видит админку"
    # Стили и premium-иконки на кнопках
    first = sent[-1].reply_markup.inline_keyboard[0][0]
    assert first.style == "primary" and first.icon_custom_emoji_id


async def test_owner_sees_admin_button(app):
    await feed(app, message_update(OWNER, "/start"))
    rows = buttons(app.session.to(OWNER_ID, SendMessage)[-1])
    assert any("Админ-панель" in b for row in rows for b in row)


async def test_about_lists_real_projects(app):
    user = tg_user(2002)
    await feed(app, callback_update(user, MenuCB(section="about").pack()))
    text = app.session.of(EditMessageText)[-1].text
    for name in ("MOG BATTLE", "Emoji Solutions Maker", "@mogbattle_robot", "@emojimakerobot", "15 000"):
        assert name in text
    assert len(text) <= 4096
    projects = await repo_call(app, lambda r: r.projects.all())
    await feed(app, callback_update(user, ProjectCB(id=projects[0].id).pack()))
    assert "MOG BATTLE" in app.session.of(EditMessageText)[-1].text


async def test_ads_prices(app):
    user = tg_user(2003)
    await feed(app, callback_update(user, MenuCB(section="ads").pack()))
    edit = app.session.of(EditMessageText)[-1]
    for price in ("150 ₽", "800 ₽", "1 200 ₽", "200 ₽", "900 ₽", "1 300 ₽", "2 000 ₽", "4 000 ₽", "1 000 ₽",
                  "проходит проверку"):
        assert price in edit.text
    assert any("Заказать рекламу" in b for row in buttons(edit) for b in row)


async def test_portfolio_links(app):
    user = tg_user(2004)
    await feed(app, callback_update(user, MenuCB(section="portfolio").pack()))
    markup = app.session.of(EditMessageText)[-1].reply_markup
    urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
    assert "https://jentiazzz-debug.github.io/solutions/" in urls
    assert "https://t.me/+xLZCiaRHdjdmMWVi" in urls


# ------------------------------------------------------------------ тикеты


async def test_ticket_creation_notifies_admin(app):
    user = tg_user(3001, "bob")
    ticket_id = await create_ticket(app, user)
    assert ticket_id == 1001, "номера тикетов начинаются с 1001"
    admin_texts = all_texts(app, OWNER_ID)
    assert f"Новый тикет #{ticket_id}" in admin_texts and "@bob" in admin_texts
    notify = [m for m in app.session.to(OWNER_ID, SendMessage) if "Новый тикет" in m.text][-1]
    assert [b for row in buttons(notify) for b in row] == ["Открыть тикет", "Ответить", "Закрыть"]
    copies = app.session.to(OWNER_ID, CopyMessage)
    assert copies and copies[-1].from_chat_id == user.id
    assert f"Обращение #{ticket_id} создано" in all_texts(app, user.id)
    ticket = await repo_call(app, lambda r: r.tickets.get(ticket_id))
    assert ticket.status == TicketStatus.OPEN.value and ticket.category_title == "Проблема с ботом"


async def test_ticket_limit_three(app):
    user = tg_user(3002, "carl")
    for i in range(3):
        await create_ticket(app, user, f"вопрос {i}")
    assert await repo_call(app, lambda r: r.tickets.count_active_for_user(user.id)) == 3
    await feed(app, callback_update(user, SupportCB(action="new").pack()))
    assert "максимального количества активных обращений" in app.session.of(EditMessageText)[-1].text
    # Даже если прислать категорию напрямую — тикет не создастся
    cats = await repo_call(app, lambda r: r.categories.all())
    await feed(app, callback_update(user, SupportCB(action="cat", id=cats[0].id).pack()))
    await feed(app, message_update(user, "четвёртый"))
    assert await repo_call(app, lambda r: r.tickets.count_active_for_user(user.id)) == 3


async def test_album_creates_single_ticket(app):
    user = tg_user(3003)
    cats = await repo_call(app, lambda r: r.categories.all())
    await feed(app, callback_update(user, SupportCB(action="new").pack()))
    await feed(app, callback_update(user, SupportCB(action="cat", id=cats[0].id).pack()))
    await asyncio.gather(*[
        feed(app, message_update(user, photo=f"ph{i}", media_group_id="album1")) for i in range(4)
    ])
    tickets = await repo_call(app, lambda r: r.tickets.active_for_user(user.id))
    assert len(tickets) == 1
    assert await repo_call(app, lambda r: r.tickets.count_messages(tickets[0].id)) == 4


async def test_user_media_goes_to_admin_and_admin_replies(app):
    user = tg_user(3004, "dina")
    tid = await create_ticket(app, user)
    app.session.clear()

    # Пользователь дописывает фото и стикер — без сценария, в активный тикет
    await feed(app, message_update(user, photo="PHOTO_1", caption="скрин ошибки"))
    await feed(app, message_update(user, sticker="STICKER_1"))
    copies = app.session.to(OWNER_ID, CopyMessage)
    assert len(copies) == 2
    reply_btn = copies[0].reply_markup.inline_keyboard[0][0]
    assert f"#{tid}" in reply_btn.text

    # Админ: «Ответить» → режим ответа → фото
    await feed(app, callback_update(OWNER, TicketCB(action="reply", id=tid).pack()))
    await feed(app, message_update(OWNER, photo="ADMIN_PHOTO", caption="Вот решение"))
    to_user = app.session.to(user.id, CopyMessage)
    assert to_user and to_user[-1].from_chat_id == OWNER_ID
    ticket = await repo_call(app, lambda r: r.tickets.get(tid))
    assert ticket.status == TicketStatus.IN_PROGRESS.value and ticket.assigned_admin_id == OWNER_ID

    # Ответ через reply на копию сообщения пользователя (без режима ответа)
    await feed(app, message_update(OWNER, "/cancel"))
    copy_id_in_admin_chat = (await repo_call(app, lambda r: r.session.execute(
        __import__("sqlalchemy").text("select message_id from ticket_message_links where chat_id=:c order by id desc"),
        {"c": OWNER_ID}))).scalars().first()
    app.session.clear()
    await feed(app, message_update(OWNER, "Текстовый ответ reply-ем", reply_to=copy_id_in_admin_chat))
    assert app.session.to(user.id, CopyMessage), "reply на сообщение пользователя уходит в тикет"

    # История хранит все типы
    msgs = await repo_call(app, lambda r: r.tickets.messages(tid))
    types = [m.content_type for m in msgs]
    assert {"text", "photo", "sticker"} <= set(types)
    assert any(m.sender_type == "admin" and m.content_type == "photo" for m in msgs)


async def test_user_reply_to_admin_message(app):
    user = tg_user(3005)
    tid1 = await create_ticket(app, user, "первый")
    tid2 = await create_ticket(app, user, "второй")
    await feed(app, callback_update(OWNER, TicketCB(action="reply", id=tid1).pack()))
    await feed(app, message_update(OWNER, "ответ в первый"))
    copy_to_user = app.session.to(user.id, CopyMessage)[-1]
    link_msg = (await repo_call(app, lambda r: r.session.execute(__import__("sqlalchemy").text(
        "select message_id from ticket_message_links where chat_id=:c and ticket_id=:t"),
        {"c": user.id, "t": tid1}))).scalars().first()
    assert copy_to_user is not None and link_msg
    # Активный тикет пользователя — второй, но reply адресует первому
    await feed(app, message_update(user, "уточнение к первому", reply_to=link_msg))
    last = (await repo_call(app, lambda r: r.tickets.messages(tid1, newest_first=True, limit=1)))[0]
    assert last.text == "уточнение к первому"
    assert tid2 != tid1


async def test_quick_reply_create_and_send(app):
    user = tg_user(3006)
    tid = await create_ticket(app, user)
    await feed(app, callback_update(OWNER, AdminCB(section="qr", action="new").pack()))
    await feed(app, message_update(OWNER, "Приветствие"))
    await feed(app, message_update(OWNER, "Здравствуйте! Уже разбираемся 🙌",
                                   entities=[MessageEntity(type="bold", offset=0, length=12)]))
    quick = (await repo_call(app, lambda r: r.quick_replies.all()))[0]
    assert quick.title == "Приветствие" and "<b>" in quick.html
    # переименование
    await feed(app, callback_update(OWNER, AdminCB(section="qr", action="rename", id=quick.id).pack()))
    await feed(app, message_update(OWNER, "Привет"))
    assert (await repo_call(app, lambda r: r.quick_replies.get(quick.id))).title == "Привет"
    app.session.clear()
    await feed(app, callback_update(OWNER, TicketCB(action="qsend", id=tid, extra=quick.id).pack()))
    assert any("Уже разбираемся" in (m.text or "") for m in app.session.to(user.id, SendMessage))
    # удаление
    await feed(app, callback_update(OWNER, AdminCB(section="qr", action="delok", id=quick.id).pack()))
    assert not await repo_call(app, lambda r: r.quick_replies.all())


async def test_admin_close_with_reason(app):
    user = tg_user(3007)
    tid = await create_ticket(app, user)
    await feed(app, callback_update(OWNER, TicketCB(action="closer", id=tid).pack()))
    await feed(app, message_update(OWNER, "Решено"))
    ticket = await repo_call(app, lambda r: r.tickets.get(tid))
    assert ticket.status == TicketStatus.CLOSED.value and ticket.close_reason == "Решено" and ticket.closed_at
    assert "закрыто" in all_texts(app, user.id) and "Решено" in all_texts(app, user.id)
    # сообщение в закрытый тикет не уходит — просим создать новый
    app.session.clear()
    await feed(app, message_update(user, "а ещё вопрос"))
    assert "создайте обращение" in all_texts(app, user.id).lower()


async def test_user_closes_own_ticket_only(app):
    user = tg_user(3008)
    stranger = tg_user(3009)
    tid = await create_ticket(app, user)
    await feed(app, callback_update(stranger, SupportCB(action="close_yes", id=tid).pack()))
    assert (await repo_call(app, lambda r: r.tickets.get(tid))).is_active, "чужой тикет закрыть нельзя"
    await feed(app, callback_update(user, SupportCB(action="close_yes", id=tid).pack()))
    assert not (await repo_call(app, lambda r: r.tickets.get(tid))).is_active


async def test_ban_and_unban(app):
    user = tg_user(3010, "spammer")
    tid = await create_ticket(app, user)
    await feed(app, callback_update(OWNER, TicketCB(action="ban", id=tid).pack()))
    await feed(app, message_update(OWNER, "спам"))
    ticket = await repo_call(app, lambda r: r.tickets.get(tid))
    assert ticket.status == TicketStatus.BANNED.value
    assert await repo_call(app, lambda r: r.bans.is_banned(user.id))
    assert "ограничен" in all_texts(app, user.id)
    await feed(app, callback_update(user, SupportCB(action="new").pack()))
    assert "ограничен" in app.session.of(EditMessageText)[-1].text
    await feed(app, message_update(user, "эй"))
    assert await repo_call(app, lambda r: r.tickets.count_active_for_user(user.id)) == 0
    # разблокировка из раздела «Блокировки»
    await feed(app, callback_update(OWNER, AdminCB(section="bans", action="unban", id=user.id).pack()))
    assert not await repo_call(app, lambda r: r.bans.is_banned(user.id))
    await create_ticket(app, user, "я исправился")
    assert await repo_call(app, lambda r: r.tickets.count_active_for_user(user.id)) == 1


async def test_ticket_search_and_filters(app):
    user = tg_user(3011, "searchme")
    tid = await create_ticket(app, user)
    await feed(app, callback_update(OWNER, AdminCB(section="tickets", action="OPEN").pack()))
    edit = app.session.of(EditMessageText)[-1]
    assert any(f"#{tid}" in b for row in buttons(edit) for b in row)
    await feed(app, callback_update(OWNER, AdminCB(section="tickets", action="search").pack()))
    await feed(app, message_update(OWNER, "@searchme"))
    last = app.session.to(OWNER_ID, SendMessage)[-1]
    assert "найдено 1" in last.text
    await feed(app, callback_update(OWNER, AdminCB(section="tickets", action="search").pack()))
    await feed(app, message_update(OWNER, str(user.id)))
    assert "найдено 1" in app.session.to(OWNER_ID, SendMessage)[-1].text
    await feed(app, callback_update(OWNER, AdminCB(section="tickets", action="search").pack()))
    await feed(app, message_update(OWNER, f"#{tid}"))
    assert "найдено 1" in app.session.to(OWNER_ID, SendMessage)[-1].text
    # карточка + история
    await feed(app, callback_update(OWNER, TicketCB(action="open", id=tid, page=1).pack()))
    assert f"Тикет #{tid}" in app.session.of(EditMessageText)[-1].text
    await feed(app, callback_update(OWNER, TicketCB(action="hist", id=tid).pack()))
    assert "История" in app.session.of(EditMessageText)[-1].text
    await feed(app, callback_update(OWNER, TicketCB(action="links", id=tid).pack()))
    links = app.session.to(OWNER_ID, SendMessage)[-1].text
    assert "t.me/nudick?text=" in links and f"start=t{tid}" in links


async def test_deep_link_opens_own_ticket(app):
    user = tg_user(3012)
    tid = await create_ticket(app, user)
    app.session.clear()
    await feed(app, message_update(user, f"/start t{tid}"))
    assert f"Обращение #{tid}" in all_texts(app, user.id)
    other = tg_user(3013)
    await feed(app, message_update(other, f"/start t{tid}"))
    assert f"Обращение #{tid}" not in all_texts(app, other.id)
    await feed(app, message_update(OWNER, f"/start adm{tid}"))
    assert f"Тикет #{tid}" in all_texts(app, OWNER_ID)


# ------------------------------------------------------------------ безопасность


async def test_non_admin_cannot_use_admin(app):
    user = tg_user(4001)
    await feed(app, message_update(user, "/admin"))
    assert "Админ-панель" not in all_texts(app, user.id)
    await feed(app, callback_update(user, AdminCB(section="stats").pack()))
    answer = app.session.of(AnswerCallbackQuery)[-1]
    assert "устарела" in (answer.text or "")
    tid = await create_ticket(app, user)
    await feed(app, callback_update(user, TicketCB(action="ban", id=tid).pack()))
    assert not await repo_call(app, lambda r: r.bans.is_banned(user.id))


async def test_forged_callback_is_rejected(app):
    user = tg_user(4002)
    await feed(app, callback_update(user, "s:open:notanumber"))
    assert "устарела" in (app.session.of(AnswerCallbackQuery)[-1].text or "")


async def test_owner_manages_admins(app):
    new_admin = tg_user(4003, "helper")
    await feed(app, message_update(new_admin, "/start"))
    await feed(app, callback_update(OWNER, AdminCB(section="admins", action="add").pack()))
    await feed(app, message_update(OWNER, "@helper"))
    assert app.ctx.admins.is_admin(new_admin.id)
    # обычный админ не управляет админами
    await feed(app, callback_update(new_admin, AdminCB(section="admins", action="add").pack()))
    assert "устарела" in (app.session.of(AnswerCallbackQuery)[-1].text or "")
    await feed(app, callback_update(OWNER, AdminCB(section="admins", action="remove", id=new_admin.id).pack()))
    assert not app.ctx.admins.is_admin(new_admin.id)


# ------------------------------------------------------------------ рассылка


async def test_broadcast_counts_and_blocked(app):
    users = [tg_user(5000 + i) for i in range(5)]
    for u in users:
        await feed(app, message_update(u, "/start"))
    app.session.blocked.add(users[2].id)
    await feed(app, callback_update(OWNER, AdminCB(section="bc", action="new").pack()))
    await feed(app, message_update(OWNER, photo="BC_PHOTO", caption="Большое обновление!"))
    await feed(app, message_update(OWNER, "Канал - https://t.me/channel | Сайт - https://example.com\nБот - https://t.me/bot"))
    await feed(app, callback_update(OWNER, AdminCB(section="bc", action="ask").pack()))
    assert "Вы уверены" in app.session.of(EditMessageText)[-1].text
    await feed(app, callback_update(OWNER, AdminCB(section="bc", action="go").pack()))
    await asyncio.wait_for(app.ctx.broadcaster._task, timeout=10)
    b = (await repo_call(app, lambda r: r.broadcasts.recent(1)))[0]
    assert b.status == "done"
    assert b.total == 6  # 5 пользователей + владелец
    assert b.blocked == 1 and b.sent == 5 and b.failed == 0
    copies = [c for c in app.session.of(CopyMessage) if c.from_chat_id == OWNER_ID and c.chat_id in {u.id for u in users}]
    assert len(copies[0].reply_markup.inline_keyboard) == 2 and len(copies[0].reply_markup.inline_keyboard[0]) == 2
    blocked_user = await repo_call(app, lambda r: r.users.get(users[2].id))
    assert blocked_user.is_blocked_bot
    assert "Рассылка завершена" in app.session.of(EditMessageText)[-1].text


# ------------------------------------------------------------------ проекты, меню, настройки


async def test_project_wizard_and_edit(app):
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="new").pack()))
    for value in ("Новый бот", "Описание нового бота", "@new_super_bot", "2 500", "-"):
        await feed(app, message_update(OWNER, value))
    await feed(app, message_update(OWNER, photo="PROJECT_IMG"))
    projects = await repo_call(app, lambda r: r.projects.all())
    p = projects[-1]
    assert (p.title, p.bot_username, p.users_count, p.url, p.image_file_id) == (
        "Новый бот", "new_super_bot", 2500, "https://t.me/new_super_bot", "PROJECT_IMG")
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="edit", id=p.id, extra="users_count").pack()))
    await feed(app, message_update(OWNER, "не число"))
    assert "целое число" in app.session.to(OWNER_ID, SendMessage)[-1].text
    await feed(app, message_update(OWNER, "3000"))
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="links", id=p.id).pack()))
    await feed(app, message_update(OWNER, "Канал - https://t.me/newchan"))
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="up", id=p.id).pack()))
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="toggle", id=p.id).pack()))
    p2 = await repo_call(app, lambda r: r.projects.get(p.id))
    assert p2.users_count == 3000 and p2.extra_links == [{"title": "Канал", "url": "https://t.me/newchan"}]
    assert not p2.is_visible
    order = [x.id for x in await repo_call(app, lambda r: r.projects.all())]
    assert order.index(p.id) == len(order) - 2
    # скрытый проект не виден пользователю
    await feed(app, callback_update(tg_user(6001), MenuCB(section="about").pack()))
    assert "Новый бот" not in app.session.of(EditMessageText)[-1].text
    await feed(app, callback_update(OWNER, AdminCB(section="proj", action="delok", id=p.id).pack()))
    assert await repo_call(app, lambda r: r.projects.get(p.id)) is None


async def test_menu_editor(app):
    buttons_ = await repo_call(app, lambda r: r.menu.all())
    ads = next(b for b in buttons_ if b.key == "ads")
    await feed(app, callback_update(OWNER, AdminCB(section="menu", action="text", id=ads.id).pack()))
    await feed(app, message_update(OWNER, "Реклама у нас"))
    await feed(app, callback_update(OWNER, AdminCB(section="menu", action="style", id=ads.id).pack()))
    await feed(app, callback_update(OWNER, AdminCB(section="menu", action="icon", id=ads.id).pack()))
    await feed(app, message_update(OWNER, "🔥", entities=[
        MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="5008069649686858594")]))
    await feed(app, callback_update(OWNER, AdminCB(section="menu", action="newlink").pack()))
    await feed(app, message_update(OWNER, "Наш сайт - https://example.com"))
    about = next(b for b in buttons_ if b.key == "about")
    await feed(app, callback_update(OWNER, AdminCB(section="menu", action="toggle", id=about.id).pack()))
    ads2 = await repo_call(app, lambda r: r.menu.get(ads.id))
    assert ads2.text == "Реклама у нас" and ads2.style == "danger" and ads2.icon_emoji_id == "5008069649686858594"
    user = tg_user(6002)
    await feed(app, message_update(user, "/start"))
    rows = buttons(app.session.to(user.id, SendMessage)[-1])
    flat = [b for row in rows for b in row]
    assert "О нас" not in flat and "Реклама у нас" in flat and "Наш сайт" in flat


async def test_texts_and_settings(app):
    await feed(app, callback_update(OWNER, AdminCB(section="texts", action="edit", extra="welcome_text").pack()))
    await feed(app, message_update(OWNER, "Привет из теста", entities=[MessageEntity(type="italic", offset=0, length=6)]))
    await feed(app, callback_update(OWNER, AdminCB(section="set", action="limit").pack()))
    await feed(app, message_update(OWNER, "5"))
    await feed(app, callback_update(OWNER, AdminCB(section="set", action="username").pack()))
    await feed(app, message_update(OWNER, "@new_support"))
    await feed(app, callback_update(OWNER, AdminCB(section="cats", action="new").pack()))
    await feed(app, message_update(OWNER, "🧾 Оплата"))
    assert await repo_call(app, lambda r: r.settings.get("welcome_text")) == "<i>Привет</i> из теста"
    assert await repo_call(app, lambda r: r.settings.get("max_tickets")) == "5"
    assert await repo_call(app, lambda r: r.settings.get("support_username")) == "new_support"
    cats = await repo_call(app, lambda r: r.categories.all())
    assert cats[-1].title == "Оплата" and cats[-1].emoji == "🧾"


# ------------------------------------------------------------------ premium emoji, статистика


async def test_premium_emoji_fallback(app):
    app.session.refuse_premium = True
    user = tg_user(7001)
    await feed(app, message_update(user, "/start"))
    sent = app.session.to(user.id, SendMessage)
    assert len(sent) >= 2, "после отказа сообщение отправлено повторно"
    last = sent[-1]
    assert "<tg-emoji" not in last.text
    assert all(not b.icon_custom_emoji_id for row in last.reply_markup.inline_keyboard for b in row)
    # дальше premium выключен — без повторных отказов
    app.session.clear()
    await feed(app, message_update(user, "/start"))
    assert len(app.session.to(user.id, SendMessage)) == 1


async def test_stats_and_chart(app):
    await create_ticket(app, tg_user(8001))
    await feed(app, callback_update(OWNER, AdminCB(section="stats").pack()))
    text = app.session.of(EditMessageText)[-1].text
    assert "Всего:" in text and "Сообщений в поддержке" in text
    await feed(app, callback_update(OWNER, AdminCB(section="stats", action="chart", page=30).pack()))
    photo = app.session.of(SendPhoto)[-1]
    assert photo.photo.data[:8] == b"\x89PNG\r\n\x1a\n"


async def test_account_section_without_config(app):
    await feed(app, callback_update(OWNER, AdminCB(section="acc").pack()))
    assert "не настроена" in app.session.of(EditMessageText)[-1].text
