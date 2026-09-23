"""Единая точка доступа к репозиториям в рамках одной сессии БД.

Хендлеры получают объект `repo: Repo` из DbSessionMiddleware и работают
только через него — прямых запросов SQL в хендлерах нет.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.content import (
    AccountRepository,
    BroadcastRepository,
    MenuButtonRepository,
    PortfolioLinkRepository,
    ProjectRepository,
    QuickReplyRepository,
    SettingsRepository,
)
from database.repositories.tickets import CategoryRepository, TicketFilter, TicketRepository
from database.repositories.users import AdminRepository, BanRepository, UserRepository


class Repo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    @cached_property
    def users(self) -> UserRepository:
        return UserRepository(self.session)

    @cached_property
    def admins(self) -> AdminRepository:
        return AdminRepository(self.session)

    @cached_property
    def bans(self) -> BanRepository:
        return BanRepository(self.session)

    @cached_property
    def categories(self) -> CategoryRepository:
        return CategoryRepository(self.session)

    @cached_property
    def tickets(self) -> TicketRepository:
        return TicketRepository(self.session)

    @cached_property
    def projects(self) -> ProjectRepository:
        return ProjectRepository(self.session)

    @cached_property
    def links(self) -> PortfolioLinkRepository:
        return PortfolioLinkRepository(self.session)

    @cached_property
    def menu(self) -> MenuButtonRepository:
        return MenuButtonRepository(self.session)

    @cached_property
    def quick_replies(self) -> QuickReplyRepository:
        return QuickReplyRepository(self.session)

    @cached_property
    def settings(self) -> SettingsRepository:
        return SettingsRepository(self.session)

    @cached_property
    def broadcasts(self) -> BroadcastRepository:
        return BroadcastRepository(self.session)

    @cached_property
    def accounts(self) -> AccountRepository:
        return AccountRepository(self.session)


__all__ = ["Repo", "TicketFilter"]
