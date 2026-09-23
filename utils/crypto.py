"""Шифрование Telethon-сессий (Fernet: AES-128-CBC + HMAC-SHA256)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SessionCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as error:
            raise ValueError(
                "SESSION_ENCRYPTION_KEY некорректен. Сгенерируйте ключ: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            ) from error

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as error:
            raise ValueError("Не удалось расшифровать сессию — ключ изменился?") from error
