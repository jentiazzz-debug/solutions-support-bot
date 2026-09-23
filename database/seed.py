"""Начальное наполнение БД.

Проекты и тексты взяты из материалов сообщества Solutions (по состоянию
на 22.09.2026):
  • канал «Solutions Studio Project [SSP]» — https://t.me/+xLZCiaRHdjdmMWVi
  • чат «Solutionss Chat» — https://t.me/+zDC0T-N-T5M4ZGUy
  • сайт-портфолио — https://jentiazzz-debug.github.io/solutions/
Ничего сверх этих источников не добавлено. Всё редактируется в админке.

Наполнение выполняется один раз (ключ seed_version в bot_settings) —
повторный запуск не перезапишет правки администратора.
"""

from __future__ import annotations

import logging

from config import Settings
from config import emoji as E
from database.repositories import Repo

log = logging.getLogger(__name__)

SEED_VERSION = "1"

DEFAULT_PORTFOLIO_URL = "https://jentiazzz-debug.github.io/solutions/"
DEFAULT_CHANNEL_URL = "https://t.me/+xLZCiaRHdjdmMWVi"
DEFAULT_CHAT_URL = "https://t.me/+zDC0T-N-T5M4ZGUy"
EMOJI_PACK_URL = "https://t.me/addemoji/solutions_project_by_Solutmark_bot"

WELCOME_TEXT = (
    f"{E.SOLUTIONS_EMOJI} <b>Solutions Studio Project</b>\n\n"
    "Студия Telegram-ботов, мини-приложений и автоматизации.\n\n"
    "Здесь можно узнать о наших проектах, посмотреть портфолио "
    "и написать в поддержку — выберите раздел ниже."
)

ABOUT_TEXT = (
    f"{E.ABOUT_EMOJI} <b>О нас</b>\n\n"
    "<b>Solutions</b> — студия Telegram-ботов. Делаем ботов любой сложности под ключ, "
    "мини-приложения внутри Telegram с оплатой звёздами, сайты и автоматизацию "
    "рабочих процессов.\n\n"
    "Наши боты работают прямо в чатах: баттлы профилей, генератор анимированных "
    "эмодзи, поиск ников, нарезка фото для сторис и другие утилиты.\n\n"
    "Стек: Python, Node.js, JavaScript, Java, PHP.\n"
    "Заказать бота — от 300 ₽, связь: @nudick"
)

SUPPORT_TEXT = (
    f"{E.SUPPORT_EMOJI} <b>Поддержка</b>\n\n"
    "Опишите проблему или вопрос — ответим прямо здесь, в этом чате.\n"
    "Выберите действие:"
)

PORTFOLIO_TEXT = (
    f"{E.PORTFOLIO_EMOJI} <b>Наше портфолио</b>\n\n"
    "Все проекты, кейсы и цены — на сайте и в Telegram-канале."
)

ADS_TEXT = (
    f"{E.ADS_EMOJI} <b>Реклама</b>\n\n"
    f"{E.CHANNEL_EMOJI} <b>Пост в Telegram-канале</b>\n"
    "• 1 час — <b>150 ₽</b>\n"
    "• 12 часов — <b>800 ₽</b>\n"
    "• 24 часа — <b>1 200 ₽</b>\n\n"
    f"{E.BOT_EMOJI} <b>Обязательная подписка в ботах</b>\n"
    "• 1 час — <b>200 ₽</b> · приход 50–100 чел.\n"
    "• 12 часов — <b>900 ₽</b> · приход 150–250 чел.\n"
    "• 24 часа — <b>1 300 ₽</b> · приход ≈700 чел.\n"
    "• 2 суток — <b>2 000 ₽</b> · приход 1–1,5 тыс. чел.\n"
    "• Неделя — <b>4 000 ₽</b> · приход 3,5–6 тыс. чел.\n\n"
    f"{E.BROADCAST_EMOJI} <b>Рассылка в ботах</b>\n"
    "• 1 рассылка — <b>1 000 ₽</b> · охват ≈20 тыс. пользователей\n\n"
    f"{E.SHIELD_EMOJI} Каждая реклама проходит проверку перед размещением.\n"
    "Приход указан средний и не гарантируется."
)

CATEGORIES: list[tuple[str, str]] = [
    ("❓", "Общий вопрос"),
    ("🤖", "Проблема с ботом"),
    ("🐞", "Ошибка"),
    ("💡", "Предложение"),
    ("🤝", "Сотрудничество"),
    ("📢", "Реклама"),
    ("📌", "Другое"),
]

PROJECTS: list[dict] = [
    {
        "title": "MOG BATTLE",
        "bot_username": "mogbattle_robot",
        "users_count": 15000,
        "description": (
            "Сравнивает два Telegram-профиля по семи метрикам — аватар, юзернейм, "
            "NFT-подарки, дата регистрации и другие — и выдаёт карточку с победителем. "
            "Работает прямо в чатах: вызов бросается одним словом «мог». "
            "Лестница лиг от SUB-3 до TRUE ADAM, рейтинг /top, редкие карточки за серии побед."
        ),
    },
    {
        "title": "Emoji Solutions Maker",
        "bot_username": "emojimakerobot",
        "users_count": 3000,
        "description": (
            "Генератор анимированных эмодзи с любым текстом в мини-приложении: "
            "700+ шаблонов, текст до 20 символов, выбор цвета с живым превью — "
            "бот сам соберёт пак. Первые 3 эмодзи бесплатно, дальше — за звёзды."
        ),
    },
    {
        "title": "Solutions Stories",
        "bot_username": "SolutionsStoriesbot",
        "users_count": None,
        "description": (
            "Нарезка фото для сторис и Canvas Story: присылаете фото, выбираете, "
            "на сколько частей резать, — получаете готовые файлы и выкладываете сверху вниз."
        ),
    },
    {
        "title": "Solutions Search",
        "bot_username": "SolutionsSearchBot",
        "users_count": None,
        "description": (
            "Поиск свободных юзернеймов и их оценка: подбор по длине, фильтр по маске, "
            "«ловушка» — уведомление, когда нужный ник освободится, оценка своего ника."
        ),
    },
    {
        "title": "Find Virus Referal",
        "bot_username": "findreferal_robot",
        "users_count": 1500,
        "description": (
            "Поиск рефералов: помогает находить людей по реферальным ссылкам "
            "и вести учёт приглашённых."
        ),
    },
    {
        "title": "Scan My ID",
        "bot_username": "ScanMyIdRobot",
        "users_count": None,
        "description": (
            "Узнать Telegram ID любого пользователя, канала, группы или бота — "
            "в одно сообщение."
        ),
    },
    {
        "title": "Solutions AutoPosting",
        "bot_username": "AutoPosting_Chatbot",
        "users_count": None,
        "description": (
            "Автоматический постинг сообщений в Telegram-чаты по расписанию. "
            "Управление и поддержка — в мини-приложении."
        ),
    },
    {
        "title": "Solutions Savemode",
        "bot_username": "SaveBot_ChatBot",
        "users_count": None,
        "description": "Свежий проект студии — сейчас в разработке.",
    },
]


async def seed_defaults(repo: Repo, settings: Settings) -> bool:
    """Заполнить пустую БД. Возвращает True, если наполнение выполнялось."""
    if await repo.settings.get("seed_version") is not None:
        return False

    await repo.settings.set("welcome_text", WELCOME_TEXT)
    await repo.settings.set("about_text", ABOUT_TEXT)
    await repo.settings.set("support_text", SUPPORT_TEXT)
    await repo.settings.set("portfolio_text", PORTFOLIO_TEXT)
    await repo.settings.set("ads_text", ADS_TEXT)
    await repo.settings.set("support_username", settings.support_username or "nudick")

    if not await repo.categories.all():
        for emoji, title in CATEGORIES:
            await repo.categories.create(title=title, emoji=emoji)

    if not await repo.menu.all():
        await repo.menu.create(
            key="about", text="О нас", style="primary", icon_emoji_id=E.ABOUT_EMOJI.custom_id
        )
        # «Реклама» — вторым рядом, как просили.
        await repo.menu.create(
            key="ads", text="Реклама", style="success", icon_emoji_id=E.ADS_EMOJI.custom_id
        )
        await repo.menu.create(
            key="support", text="Поддержка", style=None, icon_emoji_id=E.SUPPORT_EMOJI.custom_id
        )
        await repo.menu.create(
            key="portfolio",
            text="Наше портфолио",
            style="primary",
            icon_emoji_id=E.PORTFOLIO_EMOJI.custom_id,
        )

    if not await repo.links.all():
        await repo.links.create(
            title="Сайт с портфолио",
            url=settings.portfolio_url or DEFAULT_PORTFOLIO_URL,
            style="primary",
            icon_emoji_id=E.GLOBE_EMOJI.custom_id,
        )
        await repo.links.create(
            title="Telegram-канал",
            url=settings.portfolio_channel_url or DEFAULT_CHANNEL_URL,
            style="primary",
            icon_emoji_id=E.CHANNEL_EMOJI.custom_id,
        )
        await repo.links.create(
            title="Чат сообщества",
            url=settings.community_chat_url or DEFAULT_CHAT_URL,
            icon_emoji_id=E.MESSAGE_EMOJI.custom_id,
        )
        await repo.links.create(
            title="Набор эмодзи Solutions",
            url=EMOJI_PACK_URL,
            icon_emoji_id=E.STAR_EMOJI.custom_id,
        )

    if not await repo.projects.all():
        for data in PROJECTS:
            await repo.projects.create(
                **data, url=f"https://t.me/{data['bot_username']}", extra_links=[]
            )

    await repo.settings.set("seed_version", SEED_VERSION)
    await repo.commit()
    log.info("БД заполнена начальными данными")
    return True
