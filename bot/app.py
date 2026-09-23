"""Сборка приложения: бот, диспетчер, сервисы. Используется main.py и тестами."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, LinkPreviewOptions

from admin.handlers import admin_router
from admin.services.broadcast_service import BroadcastService
from bot.context import AdminCache, AppContext
from bot.handlers import fallback_router, user_routers
from bot.handlers.routing import attach
from bot.middlewares.core import DbSessionMiddleware, ThrottlingMiddleware, UserMiddleware
from bot.services.premium import PremiumEmojiMiddleware
from config.settings import Settings
from database.database import Database
from database.repositories import Repo
from database.seed import seed_defaults
from support.account_service import AccountService

log = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="support", description="Поддержка"),
]
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin", description="Админ-панель"),
    BotCommand(command="quick", description="Быстрые ответы"),
    BotCommand(command="cancel", description="Отменить действие"),
]


def make_storage(settings: Settings) -> BaseStorage:
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        log.info("FSM: Redis")
        return RedisStorage.from_url(settings.redis_url)
    log.info("FSM: память (состояния диалогов сбросятся при перезапуске)")
    return MemoryStorage()


def make_bot(settings: Settings, session=None) -> Bot:
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview=LinkPreviewOptions(is_disabled=True),
        ),
    )
    bot.session.middleware(PremiumEmojiMiddleware(enabled=settings.premium_emoji_enabled))
    return bot


@dataclass
class Application:
    bot: Bot
    dp: Dispatcher
    ctx: AppContext


async def build_app(settings: Settings, db: Database, bot: Bot, storage: BaseStorage | None = None) -> Application:
    ctx = AppContext(
        settings=settings,
        db=db,
        admins=AdminCache(settings.owner_ids),
        accounts=AccountService(settings, db),
    )
    ctx.broadcaster = BroadcastService(bot, db, settings)

    async with db.session() as session:
        repo = Repo(session)
        await seed_defaults(repo, settings)
        await ctx.admins.reload(repo)
    await ctx.broadcaster.recover()

    dp = Dispatcher(storage=storage or make_storage(settings))
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(DbSessionMiddleware(ctx))
        observer.outer_middleware(UserMiddleware())
        observer.middleware(ThrottlingMiddleware())
    attach(dp, admin_router(), *user_routers(), fallback_router())
    return Application(bot=bot, dp=dp, ctx=ctx)


async def setup_commands(bot: Bot, ctx: AppContext) -> None:
    try:
        await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    except Exception as error:  # noqa: BLE001
        log.warning("set_my_commands: %s", error)
    for admin_id in ctx.admins.all_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as error:  # noqa: BLE001 — админ мог ещё не открыть бота
            log.info("Команды для админа %s не установлены: %s", admin_id, error)
