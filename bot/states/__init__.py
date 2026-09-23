"""FSM-состояния всех многошаговых сценариев."""

from aiogram.fsm.state import State, StatesGroup


class TicketStates(StatesGroup):
    choosing_category = State()
    waiting_message = State()  # первое сообщение нового тикета


class AdminTicketStates(StatesGroup):
    replying = State()  # режим ответа в тикет
    close_reason = State()
    ban_reason = State()
    search = State()


class QuickReplyStates(StatesGroup):
    title = State()
    content = State()
    rename = State()
    edit_content = State()


class ProjectStates(StatesGroup):
    title = State()
    description = State()
    username = State()
    users = State()
    url = State()
    image = State()
    edit_field = State()
    add_link = State()


class BroadcastStates(StatesGroup):
    content = State()
    buttons = State()
    confirm = State()


class AccountStates(StatesGroup):
    phone = State()
    code = State()
    password = State()
    target = State()


class SettingsStates(StatesGroup):
    text = State()  # редактирование текстов (welcome/about/...)
    value = State()  # простые значения (username поддержки, лимит тикетов)
    media = State()  # фото/стикер приветствия


class MenuStates(StatesGroup):
    text = State()
    icon = State()
    url = State()
    new_link = State()


class CategoryStates(StatesGroup):
    create = State()
    rename = State()


class LinkStates(StatesGroup):
    create = State()
    edit_title = State()
    edit_url = State()
    icon = State()


class AdminManageStates(StatesGroup):
    add = State()
    ban_user = State()
