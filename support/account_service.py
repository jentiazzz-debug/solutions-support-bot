"""Дополнительный Telegram-аккаунт для уведомлений о новых тикетах.

Работает через официальный клиентский протокол MTProto (Telethon).
Авторизация — только владельцем аккаунта: он сам вводит номер, код из
Telegram и (если включён) пароль 2FA. Бот ничего не перехватывает и не
хранит код/пароль: они используются один раз в памяти и сразу
удаляются из чата. Сохраняется только StringSession, и только в
зашифрованном виде (Fernet, ключ SESSION_ENCRYPTION_KEY).

Если аккаунт недоступен (сессия отозвана, сеть, бан) — ошибка пишется в
лог и в карточку аккаунта, бот продолжает работать как обычно.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config.settings import Settings
from utils.crypto import SessionCipher

if TYPE_CHECKING:
    from telethon import TelegramClient

    from database.database import Database

log = logging.getLogger(__name__)

LOGIN_TTL = 600  # секунд на ввод кода
SEND_TIMEOUT = 20


class AccountError(Exception):
    """Понятная администратору ошибка подключения аккаунта."""


@dataclass
class PendingLogin:
    client: "TelegramClient"
    phone: str
    phone_code_hash: str
    started: float = field(default_factory=time.monotonic)
    needs_password: bool = False

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.started > LOGIN_TTL


@dataclass(slots=True)
class LoginResult:
    tg_user_id: int
    username: str | None
    display_name: str
    phone_masked: str
    session_encrypted: str


def mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 6:
        return "+" + "*" * len(digits)
    return f"+{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"


class AccountService:
    def __init__(self, settings: Settings, db: "Database") -> None:
        self.settings = settings
        self.db = db
        self._pending: dict[int, PendingLogin] = {}
        self._clients: dict[int, "TelegramClient"] = {}
        self._lock = asyncio.Lock()
        self._cipher: SessionCipher | None = None
        if settings.telethon_enabled:
            try:
                self._cipher = SessionCipher(settings.session_encryption_key.get_secret_value())  # type: ignore[union-attr]
            except ValueError as error:
                log.error("%s", error)

    # ------------------------------------------------------------------ state

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def unavailable_reason(self) -> str:
        if not self.settings.telegram_api_id or not self.settings.telegram_api_hash:
            return "Не заданы TELEGRAM_API_ID и TELEGRAM_API_HASH в .env (my.telegram.org → API development tools)."
        if not self.settings.session_encryption_key:
            return "Не задан SESSION_ENCRYPTION_KEY в .env — без него сессию нельзя хранить безопасно."
        return "SESSION_ENCRYPTION_KEY некорректен — см. README."

    def _new_client(self, session_string: str = "") -> "TelegramClient":
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        return TelegramClient(
            StringSession(session_string),
            self.settings.telegram_api_id,  # type: ignore[arg-type]
            self.settings.telegram_api_hash.get_secret_value(),  # type: ignore[union-attr]
            device_model="Solutions Support Notifier",
            app_version="1.0",
            receive_updates=False,
        )

    # ------------------------------------------------------------------ login

    async def begin_login(self, admin_id: int, phone: str) -> None:
        if not self.available:
            raise AccountError(self.unavailable_reason())
        from telethon import errors

        phone = "+" + "".join(ch for ch in phone if ch.isdigit())
        if len(phone) < 8:
            raise AccountError("Номер выглядит некорректно. Пример: +79991234567")
        await self.cancel_login(admin_id)
        client = self._new_client()
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
        except errors.PhoneNumberInvalidError as error:
            await client.disconnect()
            raise AccountError("Telegram не принял номер телефона.") from error
        except errors.FloodWaitError as error:
            await client.disconnect()
            raise AccountError(f"Слишком много попыток. Подождите {error.seconds} с.") from error
        except Exception as error:  # noqa: BLE001
            await client.disconnect()
            log.exception("send_code_request")
            raise AccountError(f"Не удалось запросить код: {error}") from error
        self._pending[admin_id] = PendingLogin(client, phone, sent.phone_code_hash)

    def _get_pending(self, admin_id: int) -> PendingLogin:
        pending = self._pending.get(admin_id)
        if pending is None:
            raise AccountError("Сессия входа не найдена. Начните заново.")
        if pending.expired:
            asyncio.create_task(self.cancel_login(admin_id))
            raise AccountError("Время на ввод кода истекло. Начните заново.")
        return pending

    async def submit_code(self, admin_id: int, code: str) -> LoginResult | None:
        """None — нужен пароль 2FA."""
        from telethon import errors

        pending = self._get_pending(admin_id)
        digits = "".join(ch for ch in code if ch.isdigit())
        if not 4 <= len(digits) <= 8:
            raise AccountError("Код должен состоять из 4–8 цифр.")
        try:
            await pending.client.sign_in(
                phone=pending.phone, code=digits, phone_code_hash=pending.phone_code_hash
            )
        except errors.SessionPasswordNeededError:
            pending.needs_password = True
            return None
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeEmptyError) as error:
            raise AccountError("Неверный код. Попробуйте ещё раз.") from error
        except errors.PhoneCodeExpiredError as error:
            await self.cancel_login(admin_id)
            raise AccountError(
                "Код истёк. Telegram аннулирует код, если его отправить в чат без "
                "разделителей — вводите его как 1 2 3 4 5. Начните заново."
            ) from error
        return await self._finish(admin_id)

    async def submit_password(self, admin_id: int, password: str) -> LoginResult:
        from telethon import errors

        pending = self._get_pending(admin_id)
        if not pending.needs_password:
            raise AccountError("Пароль не требуется.")
        try:
            await pending.client.sign_in(password=password)
        except errors.PasswordHashInvalidError as error:
            raise AccountError("Неверный пароль 2FA.") from error
        return await self._finish(admin_id)

    async def _finish(self, admin_id: int) -> LoginResult:
        pending = self._pending.pop(admin_id)
        client = pending.client
        try:
            me = await client.get_me()
            session_string = client.session.save()  # type: ignore[union-attr]
        finally:
            await client.disconnect()
        assert self._cipher is not None
        name = " ".join(p for p in (me.first_name, me.last_name) if p) or str(me.id)
        return LoginResult(
            tg_user_id=me.id,
            username=me.username,
            display_name=name,
            phone_masked=mask_phone(pending.phone),
            session_encrypted=self._cipher.encrypt(session_string),
        )

    async def cancel_login(self, admin_id: int) -> None:
        pending = self._pending.pop(admin_id, None)
        if pending is not None:
            try:
                await pending.client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def is_logging_in(self, admin_id: int) -> bool:
        return admin_id in self._pending

    # ------------------------------------------------------------------ send

    async def _client_for(self, account_id: int, session_encrypted: str) -> "TelegramClient":
        async with self._lock:
            client = self._clients.get(account_id)
            if client is not None and client.is_connected():
                return client
            assert self._cipher is not None
            client = self._new_client(self._cipher.decrypt(session_encrypted))
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise AccountError("Сессия аккаунта больше не действительна — подключите заново.")
            self._clients[account_id] = client
            return client

    async def _resolve_target(self, client: "TelegramClient", target: str):
        target = (target or "me").strip()
        if target.lower() in ("me", "self", "saved"):
            return "me"
        if target.lstrip("-").isdigit():
            return await client.get_input_entity(int(target))
        return await client.get_input_entity(target.lstrip("@"))

    async def send(self, account_id: int, session_encrypted: str, target: str, html: str) -> None:
        client = await self._client_for(account_id, session_encrypted)
        entity = await self._resolve_target(client, target)
        await client.send_message(entity, html, parse_mode="html", link_preview=False)

    async def notify_all(self, html: str) -> None:
        """Разослать уведомление со всех активных аккаунтов. Никогда не бросает."""
        if not self.available:
            return
        from database.repositories import Repo

        try:
            async with self.db.session() as session:
                repo = Repo(session)
                accounts = list(await repo.accounts.active())
                for account in accounts:
                    try:
                        await asyncio.wait_for(
                            self.send(
                                account.id,
                                account.session_encrypted,
                                account.notify_target or "me",
                                html,
                            ),
                            timeout=SEND_TIMEOUT,
                        )
                        if account.last_error:
                            account.last_error = None
                    except Exception as error:  # noqa: BLE001
                        log.warning("Доп. аккаунт #%s не отправил уведомление: %s", account.id, error)
                        account.last_error = str(error)[:500]
                        await self.drop_client(account.id)
                await repo.commit()
        except Exception:  # noqa: BLE001
            log.exception("Ошибка уведомления через доп. аккаунт")

    async def drop_client(self, account_id: int) -> None:
        client = self._clients.pop(account_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def logout(self, account_id: int, session_encrypted: str) -> None:
        """Завершить сессию на стороне Telegram (она исчезнет из «Устройств»)."""
        try:
            client = await self._client_for(account_id, session_encrypted)
            await client.log_out()
        except Exception as error:  # noqa: BLE001
            log.info("log_out аккаунта #%s: %s", account_id, error)
        finally:
            self._clients.pop(account_id, None)

    async def shutdown(self) -> None:
        for admin_id in list(self._pending):
            await self.cancel_login(admin_id)
        for account_id in list(self._clients):
            await self.drop_client(account_id)
