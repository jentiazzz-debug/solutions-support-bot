from __future__ import annotations

import json
from typing import Any, Sequence

from sqlalchemy import select

from database.models import (
    BotSetting,
    Broadcast,
    BroadcastResult,
    ConnectedAccount,
    MenuButton,
    PortfolioLink,
    Project,
    QuickReply,
)
from database.repositories.base import OrderedRepository, Repository


class ProjectRepository(OrderedRepository[Project]):
    model = Project


class PortfolioLinkRepository(OrderedRepository[PortfolioLink]):
    model = PortfolioLink


class MenuButtonRepository(OrderedRepository[MenuButton]):
    model = MenuButton

    async def by_key(self, key: str) -> MenuButton | None:
        return await self.session.scalar(select(MenuButton).where(MenuButton.key == key))


class QuickReplyRepository(OrderedRepository[QuickReply]):
    model = QuickReply


class SettingsRepository:
    """Хранилище key→value для текстов и настроек, редактируемых в админке."""

    def __init__(self, session) -> None:
        self.session = session

    async def get(self, key: str, default: str | None = None) -> str | None:
        row = await self.session.get(BotSetting, key)
        return row.value if row is not None and row.value is not None else default

    async def get_json(self, key: str, default: Any = None) -> Any:
        raw = await self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            return default

    async def set(self, key: str, value: str | None) -> None:
        row = await self.session.get(BotSetting, key)
        if row is None:
            self.session.add(BotSetting(key=key, value=value))
        else:
            row.value = value
        await self.session.flush()

    async def set_json(self, key: str, value: Any) -> None:
        await self.set(key, json.dumps(value, ensure_ascii=False))

    async def has(self, key: str) -> bool:
        return await self.session.get(BotSetting, key) is not None


class BroadcastRepository(Repository[Broadcast]):
    model = Broadcast

    async def recent(self, limit: int = 5) -> Sequence[Broadcast]:
        return (
            await self.session.scalars(select(Broadcast).order_by(Broadcast.id.desc()).limit(limit))
        ).all()

    async def running(self) -> Sequence[Broadcast]:
        return (
            await self.session.scalars(select(Broadcast).where(Broadcast.status == "running"))
        ).all()

    async def add_results(self, results: list[BroadcastResult]) -> None:
        self.session.add_all(results)
        await self.session.flush()


class AccountRepository(Repository[ConnectedAccount]):
    model = ConnectedAccount

    async def all(self) -> Sequence[ConnectedAccount]:
        return (
            await self.session.scalars(select(ConnectedAccount).order_by(ConnectedAccount.id))
        ).all()

    async def active(self) -> Sequence[ConnectedAccount]:
        return (
            await self.session.scalars(
                select(ConnectedAccount).where(ConnectedAccount.is_active.is_(True))
            )
        ).all()
