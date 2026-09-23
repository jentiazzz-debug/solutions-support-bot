from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Base

M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    """Общие операции для таблиц с полем id (и, если есть, position)."""

    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, obj_id: Any) -> M | None:
        return await self.session.get(self.model, obj_id)

    async def add(self, obj: M) -> M:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: M) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def update(self, obj: M, **fields: Any) -> M:
        for key, value in fields.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj


class OrderedRepository(Repository[M]):
    """Для сущностей с ручной сортировкой (поле position)."""

    async def all(self, only_enabled: bool = False) -> Sequence[M]:
        stmt = select(self.model).order_by(self.model.position, self.model.id)  # type: ignore[attr-defined]
        flag = self._enabled_column()
        if only_enabled and flag is not None:
            stmt = stmt.where(flag.is_(True))
        return (await self.session.scalars(stmt)).all()

    def _enabled_column(self):
        for name in ("is_enabled", "is_visible"):
            if hasattr(self.model, name):
                return getattr(self.model, name)
        return None

    async def next_position(self) -> int:
        value = await self.session.scalar(select(func.max(self.model.position)))  # type: ignore[attr-defined]
        return (value or 0) + 1

    async def create(self, **fields: Any) -> M:
        fields.setdefault("position", await self.next_position())
        return await self.add(self.model(**fields))

    async def move(self, obj_id: int, delta: int) -> bool:
        """Сдвинуть элемент на delta позиций (−1 — выше, +1 — ниже)."""
        items = list(await self.all())
        index = next((i for i, item in enumerate(items) if item.id == obj_id), None)  # type: ignore[attr-defined]
        if index is None:
            return False
        target = index + delta
        if not 0 <= target < len(items):
            return False
        items[index], items[target] = items[target], items[index]
        for pos, item in enumerate(items, start=1):
            item.position = pos  # type: ignore[attr-defined]
        await self.session.flush()
        return True

    async def toggle(self, obj: M) -> bool:
        flag = self._enabled_column()
        if flag is None:
            raise TypeError(f"{self.model.__name__} не поддерживает включение/выключение")
        name = flag.key
        setattr(obj, name, not getattr(obj, name))
        await self.session.flush()
        return getattr(obj, name)
