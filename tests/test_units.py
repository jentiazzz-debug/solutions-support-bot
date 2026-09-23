from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from config import emoji as E
from support.account_service import AccountService, mask_phone
from support.deeplink import parse_start_payload, support_dm_link
from utils.crypto import SessionCipher
from utils.text import normalize_username, parse_buttons


def test_session_cipher_roundtrip_and_no_plaintext():
    key = Fernet.generate_key().decode()
    cipher = SessionCipher(key)
    secret = "1ApWapzMBu4PfiXOaKlWyf87-SESSION-STRING"
    token = cipher.encrypt(secret)
    assert secret not in token
    assert cipher.decrypt(token) == secret
    with pytest.raises(ValueError):
        SessionCipher(Fernet.generate_key().decode()).decrypt(token)
    with pytest.raises(ValueError):
        SessionCipher("not-a-key")


def test_mask_phone():
    assert mask_phone("+7 999 123-45-67") == "+79*******67"


def test_account_service_disabled_without_keys(settings):
    service = AccountService(settings, db=None)  # type: ignore[arg-type]
    assert not service.available
    assert "TELEGRAM_API_ID" in service.unavailable_reason()


@pytest.mark.asyncio
async def test_account_notify_never_raises(settings, tmp_path):
    """Если доп. аккаунт недоступен — бот продолжает работать, ошибка пишется в карточку."""
    from database.database import Database, run_migrations_async
    from database.models import ConnectedAccount
    from database.repositories import Repo

    from pydantic import SecretStr

    settings.telegram_api_id = 1
    settings.telegram_api_hash = SecretStr("hash")
    settings.session_encryption_key = SecretStr(Fernet.generate_key().decode())
    await run_migrations_async(settings)
    db = Database(settings.database_url)
    service = AccountService(settings, db)
    assert service.available
    async with db.session() as session:
        repo = Repo(session)
        await repo.accounts.add(ConnectedAccount(session_encrypted=service._cipher.encrypt("x"), notify_target="me"))
        await repo.commit()

    async def broken_send(*_args, **_kwargs):
        raise ConnectionError("network down")

    service.send = broken_send  # type: ignore[method-assign]
    await service.notify_all("test")  # не бросает
    async with db.session() as session:
        account = (await Repo(session).accounts.all())[0]
        assert "network down" in (account.last_error or "")
    await db.dispose()


def test_deeplinks():
    assert parse_start_payload("t1042") == ("ticket", 1042)
    assert parse_start_payload("adm1042") == ("admin", 1042)
    assert parse_start_payload("hack") is None
    link = support_dm_link("@nudick", 1042)
    assert link.startswith("https://t.me/nudick?text=") and "%231042" in link


def test_parse_buttons():
    rows = parse_buttons("A - https://a.com | B - https://b.com\nC - tg://resolve?domain=x")
    assert [[b["text"] for b in r] for r in rows] == [["A", "B"], ["C"]]
    with pytest.raises(ValueError):
        parse_buttons("без ссылки")
    with pytest.raises(ValueError):
        parse_buttons("A - javascript:alert(1)")


def test_normalize_username():
    assert normalize_username("https://t.me/emojimakerobot") == "emojimakerobot"
    assert normalize_username("@ab") is None


def test_emoji_ids_are_from_pack():
    """Все premium-эмодзи интерфейса существуют в выгрузке набора проекта."""
    names = [v for k, v in vars(E).items() if k.endswith("_EMOJI")]
    assert names and all(e.custom_id and e.custom_id.isdigit() for e in names)


def test_migration_0002_fixes_existing_menu(settings):
    """База, созданная со старым меню, после миграции получает второй ряд «Реклама | Портфолио»."""
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from config.settings import BASE_DIR
    from database.database import Database

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.attributes["database_url"] = settings.database_url
    command.upgrade(cfg, "0001")

    old = [("about", "О нас"), ("portfolio", "Наше портфолио"), ("link", "Сайт"),
           ("ads", "Реклама"), ("support", "Поддержка")]

    async def fill_and_read(fill: bool):
        db = Database(settings.database_url)
        async with db.engine.begin() as conn:
            if fill:
                for pos, (key, title) in enumerate(old, start=1):
                    await conn.execute(text(
                        "INSERT INTO menu_buttons (key, text, position, is_enabled, row_width, created_at) "
                        "VALUES (:k, :t, :p, true, 1, CURRENT_TIMESTAMP)"), {"k": key, "t": title, "p": pos})
            rows = (await conn.execute(text("SELECT key, row_width FROM menu_buttons ORDER BY position"))).all()
        await db.dispose()
        return [tuple(r) for r in rows]

    asyncio.run(fill_and_read(True))
    command.upgrade(cfg, "head")
    assert asyncio.run(fill_and_read(False)) == [
        ("about", 1), ("ads", 2), ("portfolio", 2), ("support", 1), ("link", 1)
    ]
