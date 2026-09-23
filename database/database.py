"""Подключение к БД: движок, фабрика сессий, запуск миграций."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config.settings import BASE_DIR, Settings

log = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, echo: bool = False) -> None:
        self.url = url
        parsed = make_url(url)
        self.is_sqlite = parsed.get_backend_name() == "sqlite"
        kwargs: dict = {"echo": echo, "pool_pre_ping": True}
        if self.is_sqlite:
            database = parsed.database
            if database and database != ":memory:":
                path = Path(database)
                if not path.is_absolute():
                    path = BASE_DIR / path
                path.parent.mkdir(parents=True, exist_ok=True)
                url = str(parsed.set(database=str(path)))
            kwargs.pop("pool_pre_ping")
            kwargs["connect_args"] = {"timeout": 30}
        else:
            kwargs.update(pool_size=10, max_overflow=10, pool_recycle=1800)
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        if self.is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def ping(self) -> bool:
        from sqlalchemy import text

        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — healthcheck не должен падать
            log.exception("БД недоступна")
            return False

    async def dispose(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - driver-level
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def run_migrations(settings: Settings) -> None:
    """alembic upgrade head — синхронно, до старта event loop-а бота."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.attributes["database_url"] = settings.database_url
    command.upgrade(cfg, "head")


async def run_migrations_async(settings: Settings) -> None:
    await asyncio.to_thread(run_migrations, settings)
