"""Точка входа: python main.py"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from config import get_settings
from utils.logging import setup_logging

log = logging.getLogger("main")


async def run() -> None:
    from aiogram.exceptions import TelegramUnauthorizedError
    from aiogram.types import Update

    from bot.app import build_app, make_bot, setup_commands
    from bot.services.health import HealthState, start_health_server
    from database.database import Database

    settings = get_settings()
    db = Database(settings.database_url, echo=settings.db_echo)
    bot = make_bot(settings)
    app = await build_app(settings, db, bot)
    health = HealthState()

    try:
        me = await bot.me()
    except TelegramUnauthorizedError:
        log.critical("Telegram отклонил BOT_TOKEN — проверьте токен в .env (@BotFather → /mybots → API Token)")
        await bot.session.close()
        await db.dispose()
        raise SystemExit(1)
    app.ctx.bot_username = me.username or ""
    log.info("Бот @%s запущен. Админов: %s", me.username, len(app.ctx.admins.all_ids))
    if not app.ctx.admins.owners:
        log.warning("ADMIN_IDS пуст — админ-панель никому не доступна!")
    await setup_commands(bot, app.ctx)

    @app.dp.update.outer_middleware()
    async def _touch(handler, event: Update, data):
        health.touch()
        return await handler(event, data)

    @app.dp.startup()
    async def _on_startup() -> None:
        health.polling = True

    @app.dp.shutdown()
    async def _on_shutdown() -> None:
        health.polling = False
        log.info("Остановка: завершаю рассылку и сессии…")
        if app.ctx.broadcaster:
            await app.ctx.broadcaster.shutdown()
        await app.ctx.accounts.shutdown()

    runner = await start_health_server(db, health, settings.health_host, settings.health_port)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await app.dp.start_polling(
            bot,
            allowed_updates=app.dp.resolve_used_update_types(),
            handle_signals=True,
            close_bot_session=True,
        )
    finally:
        if runner is not None:
            await runner.cleanup()
        await app.dp.storage.close()
        await db.dispose()
        log.info("Бот остановлен")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)
    if os.getenv("SKIP_MIGRATIONS", "").lower() not in ("1", "true", "yes"):
        from database.database import run_migrations

        log.info("Применяю миграции БД…")
        run_migrations(settings)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
