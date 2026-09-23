"""Подключить дополнительный аккаунт из консоли сервера (без ввода кода в чат бота).

Запуск:
    docker compose exec bot python -m scripts.connect_account
    # или локально: python -m scripts.connect_account

Скрипт спросит номер, код и (если есть) пароль 2FA — всё вводит владелец
аккаунта. В БД сохраняется только зашифрованная сессия.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from database.database import Database, run_migrations  # noqa: E402
from database.models import ConnectedAccount  # noqa: E402
from database.repositories import Repo  # noqa: E402
from support.account_service import AccountError, AccountService  # noqa: E402

ADMIN_KEY = 0  # фиктивный id для консольной сессии входа


async def main() -> int:
    settings = get_settings()
    db = Database(settings.database_url)
    service = AccountService(settings, db)
    if not service.available:
        print("Ошибка:", service.unavailable_reason())
        return 1
    try:
        phone = input("Номер телефона (+79991234567): ").strip()
        await service.begin_login(ADMIN_KEY, phone)
        result = None
        while result is None:
            code = input("Код из Telegram: ").strip()
            try:
                result = await service.submit_code(ADMIN_KEY, code)
            except AccountError as error:
                print(error)
                if not service.is_logging_in(ADMIN_KEY):
                    return 1
                continue
            if result is None:
                while True:
                    password = getpass.getpass("Пароль 2FA (ввод скрыт): ")
                    try:
                        result = await service.submit_password(ADMIN_KEY, password)
                        break
                    except AccountError as error:
                        print(error)
        target = input("Куда слать уведомления (@username / id / me) [me]: ").strip() or "me"
        async with db.session() as session:
            repo = Repo(session)
            account = await repo.accounts.add(ConnectedAccount(
                tg_user_id=result.tg_user_id,
                username=result.username,
                display_name=result.display_name,
                phone_masked=result.phone_masked,
                session_encrypted=result.session_encrypted,
                notify_target=target,
            ))
            await repo.commit()
            print(f"Аккаунт {result.display_name} подключён (#{account.id}). Отправляю тест…")
            try:
                await service.send(account.id, account.session_encrypted, target,
                                   "✅ Уведомления о новых тикетах Solutions подключены.")
                print("Тест отправлен.")
            except Exception as error:  # noqa: BLE001
                print("Не удалось отправить тест:", error)
        return 0
    except AccountError as error:
        print("Ошибка:", error)
        return 1
    finally:
        await service.shutdown()
        await db.dispose()


if __name__ == "__main__":
    run_migrations(get_settings())
    sys.exit(asyncio.run(main()))
