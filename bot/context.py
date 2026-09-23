"""Общие для всего приложения объекты. Передаются в хендлеры через DI aiogram."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config.settings import Settings

if TYPE_CHECKING:
    from admin.services.broadcast_service import BroadcastService
    from database.database import Database
    from database.repositories import Repo
    from support.account_service import AccountService


class AdminCache:
    """Кто администратор. Владельцы — из ADMIN_IDS, остальные — из БД."""

    def __init__(self, owners: frozenset[int]) -> None:
        self.owners = owners
        self._db_ids: set[int] = set()

    async def reload(self, repo: "Repo") -> None:
        self._db_ids = await repo.admins.ids()

    def is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and (user_id in self.owners or user_id in self._db_ids)

    def is_owner(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.owners

    @property
    def all_ids(self) -> set[int]:
        return set(self.owners) | self._db_ids


@dataclass
class AppContext:
    settings: Settings
    db: "Database"
    admins: AdminCache
    accounts: "AccountService"
    broadcaster: "BroadcastService | None" = None
    bot_username: str = ""
    extras: dict = field(default_factory=dict)
