from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select, update

from database.models import Admin, BannedUser, User, utcnow
from database.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    async def upsert(
        self,
        user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        language_code: str | None,
    ) -> tuple[User, bool]:
        """Создать или обновить пользователя. Возвращает (user, is_new)."""
        user = await self.get(user_id)
        now = utcnow()
        if user is None:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name or "",
                last_name=last_name,
                language_code=language_code,
                created_at=now,
                last_seen_at=now,
            )
            self.session.add(user)
            await self.session.flush()
            return user, True
        user.username = username
        user.first_name = first_name or ""
        user.last_name = last_name
        user.language_code = language_code
        user.last_seen_at = now
        if user.is_blocked_bot:
            user.is_blocked_bot = False
        await self.session.flush()
        return user, False

    async def find_by_username(self, username: str) -> User | None:
        username = username.lstrip("@").lower()
        return await self.session.scalar(
            select(User).where(func.lower(User.username) == username)
        )

    async def count(self) -> int:
        return await self.session.scalar(select(func.count(User.id))) or 0

    async def count_created_since(self, since: datetime) -> int:
        return await self.session.scalar(
            select(func.count(User.id)).where(User.created_at >= since)
        ) or 0

    async def count_active_since(self, since: datetime) -> int:
        return await self.session.scalar(
            select(func.count(User.id)).where(User.last_seen_at >= since)
        ) or 0

    async def count_blocked_bot(self) -> int:
        return await self.session.scalar(
            select(func.count(User.id)).where(User.is_blocked_bot.is_(True))
        ) or 0

    async def created_dates_since(self, since: datetime) -> Sequence[datetime]:
        return (
            await self.session.scalars(select(User.created_at).where(User.created_at >= since))
        ).all()

    async def broadcast_ids(self) -> list[int]:
        rows = await self.session.scalars(
            select(User.id).where(User.is_blocked_bot.is_(False)).order_by(User.id)
        )
        return list(rows)

    async def set_blocked_bot(self, user_id: int, value: bool = True) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_blocked_bot=value)
        )

    async def set_active_ticket(self, user_id: int, ticket_id: int | None) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(active_ticket_id=ticket_id)
        )


class AdminRepository(Repository[Admin]):
    model = Admin

    async def all(self) -> Sequence[Admin]:
        return (await self.session.scalars(select(Admin).order_by(Admin.created_at))).all()

    async def ids(self) -> set[int]:
        return set(await self.session.scalars(select(Admin.user_id)))

    async def notify_ids(self) -> set[int]:
        return set(
            await self.session.scalars(select(Admin.user_id).where(Admin.notify.is_(True)))
        )

    async def ensure(self, user_id: int, added_by: int | None = None, note: str | None = None) -> Admin:
        admin = await self.get(user_id)
        if admin is None:
            admin = await self.add(Admin(user_id=user_id, added_by=added_by, note=note))
        return admin


class BanRepository(Repository[BannedUser]):
    model = BannedUser

    async def is_banned(self, user_id: int) -> bool:
        return await self.get(user_id) is not None

    async def ban(self, user_id: int, reason: str | None, banned_by: int | None) -> BannedUser:
        ban = await self.get(user_id)
        if ban is None:
            ban = await self.add(BannedUser(user_id=user_id, reason=reason, banned_by=banned_by))
        else:
            ban.reason = reason
            ban.banned_by = banned_by
            await self.session.flush()
        return ban

    async def unban(self, user_id: int) -> bool:
        ban = await self.get(user_id)
        if ban is None:
            return False
        await self.delete(ban)
        return True

    async def page(self, offset: int, limit: int) -> tuple[Sequence[BannedUser], int]:
        total = await self.session.scalar(select(func.count(BannedUser.user_id))) or 0
        rows = await self.session.scalars(
            select(BannedUser).order_by(BannedUser.created_at.desc()).offset(offset).limit(limit)
        )
        return rows.all(), total

    async def count(self) -> int:
        return await self.session.scalar(select(func.count(BannedUser.user_id))) or 0
