from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "123456:TEST")

from tests.fakes import FakeSession  # noqa: E402

OWNER_ID = 1000
ADMIN2_ID = 1001


# TEST_DATABASE_URL=postgresql+asyncpg://… — прогнать тесты на PostgreSQL
# (схема public пересоздаётся перед каждым тестом).
PG_URL = os.getenv("TEST_DATABASE_URL")


def _reset_pg_schema(url: str) -> None:
    import asyncio

    import asyncpg

    async def reset() -> None:
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.close()

    asyncio.run(reset())


@pytest.fixture
def settings(tmp_path):
    from config.settings import Settings

    if PG_URL:
        _reset_pg_schema(PG_URL)
    return Settings(
        bot_token="123456:TEST",
        admin_ids=str(OWNER_ID),
        database_url=PG_URL or f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        support_username="nudick",
        log_dir="",
        broadcast_rate=30,
        _env_file=None,
    )


@pytest_asyncio.fixture
async def app(settings):
    from aiogram.fsm.storage.memory import MemoryStorage

    from bot.app import build_app, make_bot
    from database.database import Database, run_migrations_async

    await run_migrations_async(settings)
    db = Database(settings.database_url)
    session = FakeSession()
    bot = make_bot(settings, session=session)
    application = await build_app(settings, db, bot, storage=MemoryStorage())
    application.ctx.bot_username = "test_support_bot"
    application.session = session  # type: ignore[attr-defined]
    yield application
    if application.ctx.broadcaster:
        await application.ctx.broadcaster.shutdown()
    await db.dispose()
